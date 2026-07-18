from __future__ import annotations

import hashlib
import json
import re
import tarfile
import tempfile
from pathlib import Path

import zstandard as zstd

from .model import ExecutionState

RELEASE_ZSTD_LEVEL = 3


EVIDENCE_FILES = (
    "manifest.json",
    "results.json",
    "report.md",
    "input/manifest.json",
)
ARTIFACT_ROOTS = ("artifacts", "claims", "prompt", "robustness")


def _safe_slug(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ValueError("platform must be a lowercase release slug")
    return value


def _artifact_references(manifest: dict, results: dict) -> list[tuple[str, bool]]:
    terminal_failures = {ExecutionState.FAILED, ExecutionState.UNSUPPORTED}
    references = [
        (entry["artifact"], entry.get("state") not in terminal_failures)
        for entry in manifest.get("formats", [])
        if isinstance(entry.get("artifact"), str)
    ]
    for observation in results.get("results", {}).values():
        if not isinstance(observation, dict):
            continue
        evidence = observation.get("evidence", {})
        for source in (observation, evidence):
            if not isinstance(source, dict):
                continue
            if isinstance(source.get("artifact"), str):
                references.append((source["artifact"], True))
            if isinstance(source.get("artifacts"), dict):
                references.extend(
                    (item, True)
                    for item in source["artifacts"].values()
                    if isinstance(item, str)
                )
    robustness = results.get("results", {}).get("robustness_v1", {})
    if isinstance(robustness, dict):
        for case in robustness.get("cases", []):
            if not isinstance(case, dict):
                continue
            for name in ("stdout", "stderr"):
                if isinstance(case.get(name), str):
                    references.append((case[name], True))
            input_arrow = case.get("input_arrow")
            if isinstance(input_arrow, dict) and isinstance(
                input_arrow.get("path"), str
            ):
                references.append((input_arrow["path"], True))
            for record in case.get("artifact_records", []):
                if isinstance(record, dict) and isinstance(record.get("path"), str):
                    references.append((record["path"], True))
            for record in case.get("corpus_records", []):
                if isinstance(record, dict) and isinstance(record.get("path"), str):
                    references.append((record["path"], True))
    return references


def _reject_symlink_path(path: Path, run_root: Path) -> None:
    current = run_root
    for part in path.relative_to(run_root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError(
                f"release artifact path contains a symlink: "
                f"{path.relative_to(run_root)}"
            )


def _path_files(path: Path, run_root: Path) -> set[Path]:
    _reject_symlink_path(path, run_root)
    if path.is_file():
        candidates = [path]
    elif path.is_dir():
        candidates = list(path.rglob("*"))
    else:
        raise ValueError(
            f"release artifact is not a regular file or directory: "
            f"{path.relative_to(run_root)}"
        )
    for candidate in candidates:
        _reject_symlink_path(candidate, run_root)
    files = {candidate for candidate in candidates if candidate.is_file()}
    if any(not candidate.resolve().is_relative_to(run_root) for candidate in files):
        raise ValueError("release artifact resolves outside the run directory")
    return files


def _release_files(run_dir: Path, manifest: dict, results: dict) -> list[Path]:
    if run_dir.is_symlink():
        raise ValueError("release run directory must not be a symlink")
    run_root = run_dir.resolve()
    required_files = [run_dir / relative for relative in EVIDENCE_FILES]
    for path in required_files:
        _reject_symlink_path(path, run_root)
    missing = [
        str(path.relative_to(run_dir)) for path in required_files if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(f"release evidence missing: {', '.join(missing)}")

    referenced_files = set()
    for value, must_exist in _artifact_references(manifest, results):
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError(f"release artifact path is unsafe: {value}")
        target = run_dir / relative
        _reject_symlink_path(target, run_root)
        if not target.exists() and not must_exist:
            continue
        if not target.exists() or not target.resolve().is_relative_to(run_root):
            raise FileNotFoundError(f"release artifact missing or unsafe: {value}")
        referenced_files.update(_path_files(target, run_root))

    files = set(required_files) | referenced_files
    for name in ARTIFACT_ROOTS:
        root = run_dir / name
        if root.exists() or root.is_symlink():
            files.update(_path_files(root, run_root))
    return sorted(files, key=lambda path: path.relative_to(run_dir).as_posix())


def _write_archive(
    archive_path: Path, files: list[Path], run_dir: Path, run_id: str
) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=archive_path.parent,
            prefix=f".{archive_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temporary = Path(destination.name)
            with zstd.ZstdCompressor(level=RELEASE_ZSTD_LEVEL).stream_writer(
                destination, closefd=False
            ) as compressor:
                with tarfile.open(
                    fileobj=compressor, mode="w|", format=tarfile.GNU_FORMAT
                ) as archive:
                    for path in files:
                        relative = path.relative_to(run_dir)
                        info = tarfile.TarInfo(f"{run_id}/{relative.as_posix()}")
                        info.size = path.stat().st_size
                        info.mode = 0o644
                        info.mtime = info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        with path.open("rb") as source:
                            archive.addfile(info, source)
        temporary.chmod(0o644)
        temporary.replace(archive_path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_run(run_dir: Path, output: Path, platform: str) -> Path:
    if run_dir.is_symlink():
        raise ValueError("release run directory must not be a symlink")
    run_dir = run_dir.resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if manifest["state"] != ExecutionState.REPORTED:
        raise ValueError("release packaging requires reported evidence")
    if results["state"] != ExecutionState.REPORTED:
        raise ValueError("release packaging requires reported results")
    if manifest["dataset_id"] != results["dataset_id"]:
        raise ValueError("release manifest and results dataset mismatch")

    files = _release_files(run_dir, manifest, results)

    output.mkdir(parents=True, exist_ok=True)
    name = f"data-format-lab-{results['profile']}-{_safe_slug(platform)}-{results['run_id']}"
    archive_path = output / f"{name}.tar.zst"
    _write_archive(archive_path, files, run_dir, results["run_id"])
    digest = _sha256(archive_path)
    archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="ascii"
    )
    return archive_path
