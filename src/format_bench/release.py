from __future__ import annotations

import hashlib
import io
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


def _safe_relative_path(value: str, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"{label} path is unsafe: {value}")
    return relative


def _safe_claim_segment(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ValueError(f"aggregate {label} must be a lowercase path segment")
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


def _aggregate_artifact_files(
    run_dir: Path, results: dict, source_root: Path
) -> dict[Path, Path]:
    if results.get("schema_version") != "aggregate-1":
        return {}
    datasets = results.get("datasets")
    if not isinstance(datasets, list):
        raise TypeError("aggregate results datasets must be a list")

    source_root = source_root.resolve()
    archived: dict[Path, Path] = {}
    for dataset in datasets:
        if not isinstance(dataset, dict):
            raise TypeError("aggregate dataset record must be an object")
        dataset_id = _safe_claim_segment(dataset.get("dataset_id"), "dataset_id")
        evidence_records = dataset.get("evidence")
        if not isinstance(evidence_records, list):
            raise TypeError("aggregate dataset evidence must be a list")
        for evidence in evidence_records:
            if not isinstance(evidence, dict):
                raise TypeError("aggregate evidence record must be an object")
            source = evidence.get("source")
            if source is None:
                continue
            if not isinstance(source, dict):
                raise TypeError("aggregate evidence source must be an object")
            pair = _safe_claim_segment(evidence.get("pair"), "pair")
            run_path = source.get("run_path")
            if not isinstance(run_path, str):
                raise TypeError("aggregate evidence source run_path must be a string")

            claim_root = run_dir / "claims" / dataset_id / pair
            nested_documents: list[dict] = []
            for name in ("manifest", "results"):
                path = claim_root / f"{name}.json"
                if not path.is_file():
                    raise FileNotFoundError(
                        f"aggregate claim {name} missing: {path.relative_to(run_dir)}"
                    )
                document = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(document, dict):
                    raise TypeError(f"aggregate claim {name} must be an object")
                nested_documents.append(document)
            nested_manifest, nested_results = nested_documents

            source_run_path = source_root / _safe_relative_path(
                run_path, "aggregate source run"
            )
            _reject_symlink_path(source_run_path, source_root)
            if not source_run_path.is_dir():
                raise FileNotFoundError(f"aggregate source run missing: {run_path}")
            source_run = source_run_path.resolve()
            if not source_run.is_relative_to(source_root):
                raise ValueError(f"aggregate source run path is unsafe: {run_path}")

            for value, must_exist in _artifact_references(
                nested_manifest, nested_results
            ):
                relative = _safe_relative_path(value, "aggregate artifact")
                archived_target = claim_root / relative
                source_target = source_run / relative
                if not source_target.exists() and not must_exist:
                    continue
                if not source_target.exists():
                    raise FileNotFoundError(
                        f"aggregate source artifact missing: {run_path}/{value}"
                    )
                destination_root = claim_root.relative_to(run_dir) / relative
                source_files = _path_files(source_target, source_run)
                if source_target.is_dir() and archived_target.exists():
                    if not archived_target.is_dir():
                        raise ValueError(
                            f"aggregate archive member collision: {destination_root}"
                        )
                    source_names = {
                        path.relative_to(source_target) for path in source_files
                    }
                    archived_names = {
                        path.relative_to(archived_target)
                        for path in _path_files(archived_target, run_dir)
                    }
                    if archived_names - source_names:
                        raise ValueError(
                            f"aggregate archive member collision: {destination_root}"
                        )
                for source_file in source_files:
                    destination = destination_root
                    if source_target.is_dir():
                        destination /= source_file.relative_to(source_target)
                    archived_file = run_dir / destination
                    if archived_file.exists():
                        if not archived_file.is_file() or _sha256(
                            archived_file
                        ) != _sha256(source_file):
                            raise ValueError(
                                f"aggregate archive member collision: {destination}"
                            )
                        continue
                    previous = archived.get(destination)
                    if previous is not None and previous != source_file:
                        raise ValueError(
                            f"aggregate archive member collision: {destination}"
                        )
                    archived[destination] = source_file
    return archived


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


def _archive_relative_references(value: object, run_id: str) -> object:
    prefix = f".data/{run_id}/"
    if isinstance(value, str):
        return value.removeprefix(prefix) if value.startswith(prefix) else value
    if isinstance(value, list):
        return [_archive_relative_references(item, run_id) for item in value]
    if isinstance(value, dict):
        return {
            key: _archive_relative_references(item, run_id)
            for key, item in value.items()
        }
    return value


def _archive_document(document: dict, run_id: str) -> bytes | None:
    normalized = _archive_relative_references(document, run_id)
    if normalized == document:
        return None
    return (json.dumps(normalized, indent=2, sort_keys=True) + "\n").encode("utf-8")


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
        relative = _safe_relative_path(value, "release artifact")
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
    archive_path: Path,
    files: list[Path],
    run_dir: Path,
    run_id: str,
    replacements: dict[Path, bytes],
    aggregate_artifacts: dict[Path, Path],
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
                    members = {
                        path.relative_to(run_dir): path for path in files
                    } | aggregate_artifacts
                    for relative, path in sorted(
                        members.items(), key=lambda item: item[0].as_posix()
                    ):
                        info = tarfile.TarInfo(f"{run_id}/{relative.as_posix()}")
                        replacement = replacements.get(path)
                        info.size = (
                            len(replacement)
                            if replacement is not None
                            else path.stat().st_size
                        )
                        info.mode = 0o644
                        info.mtime = info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        if replacement is not None:
                            archive.addfile(info, io.BytesIO(replacement))
                        else:
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


def package_run(
    run_dir: Path, output: Path, platform: str, *, source_root: Path = Path(".")
) -> Path:
    if run_dir.is_symlink():
        raise ValueError("release run directory must not be a symlink")
    run_dir = run_dir.resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    # LLM lifecycle contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED ->
    # BENCHMARKED -> REPORTED; UNSUPPORTED and FAILED are terminal and unrankable.
    if manifest["state"] != ExecutionState.REPORTED:
        raise ValueError("release packaging requires reported evidence")
    if results["state"] != ExecutionState.REPORTED:
        raise ValueError("release packaging requires reported results")
    if manifest["dataset_id"] != results["dataset_id"]:
        raise ValueError("release manifest and results dataset mismatch")

    # LLM lifecycle contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED ->
    # BENCHMARKED -> REPORTED. Only REPORTED evidence is packaged; UNSUPPORTED
    # and FAILED artifacts remain terminal, non-rankable exceptions.
    files = _release_files(run_dir, manifest, results)
    replacements = {}
    for path, document in (
        (run_dir / "manifest.json", manifest),
        (run_dir / "results.json", results),
    ):
        replacement = _archive_document(document, results["run_id"])
        if replacement is not None:
            replacements[path] = replacement
    aggregate_artifacts = _aggregate_artifact_files(run_dir, results, source_root)

    output.mkdir(parents=True, exist_ok=True)
    name = f"data-format-lab-{results['profile']}-{_safe_slug(platform)}-{results['run_id']}"
    archive_path = output / f"{name}.tar.zst"
    _write_archive(
        archive_path,
        files,
        run_dir,
        results["run_id"],
        replacements,
        aggregate_artifacts,
    )
    digest = _sha256(archive_path)
    archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="ascii"
    )
    return archive_path
