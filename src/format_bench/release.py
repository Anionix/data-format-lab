from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

import zstandard as zstd

from .model import ExecutionState


EVIDENCE_FILES = (
    "manifest.json",
    "results.json",
    "report.md",
    "input/manifest.json",
)
ARTIFACT_ROOTS = ("artifacts", "claims", "prompt")


def _safe_slug(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ValueError("platform must be a lowercase release slug")
    return value


def _artifact_references(payload: object) -> list[str]:
    references = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "artifact" and isinstance(value, str):
                references.append(value)
            elif key == "artifacts" and isinstance(value, dict):
                references.extend(item for item in value.values() if isinstance(item, str))
            references.extend(_artifact_references(value))
    elif isinstance(payload, list):
        for value in payload:
            references.extend(_artifact_references(value))
    return references


def _release_files(run_dir: Path, manifest: dict, results: dict) -> list[Path]:
    required = [run_dir / relative for relative in EVIDENCE_FILES]
    missing = [str(path.relative_to(run_dir)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"release evidence missing: {', '.join(missing)}")

    run_root = run_dir.resolve()
    referenced_files = set()
    for value in _artifact_references(manifest) + _artifact_references(results):
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"release artifact path is unsafe: {value}")
        target = run_dir / relative
        if not target.exists() or not target.resolve().is_relative_to(run_root):
            raise FileNotFoundError(f"release artifact missing or unsafe: {value}")
        if target.is_file():
            referenced_files.add(target)
        else:
            referenced_files.update(path for path in target.rglob("*") if path.is_file())

    files = set(required) | referenced_files
    for name in ARTIFACT_ROOTS:
        root = run_dir / name
        if root.exists():
            files.update(path for path in root.rglob("*") if path.is_file())
    if any(not path.resolve().is_relative_to(run_root) for path in files):
        raise ValueError("release artifact resolves outside the run directory")
    return sorted(files, key=lambda path: path.relative_to(run_dir).as_posix())


def package_run(run_dir: Path, output: Path, platform: str) -> Path:
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
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path in files:
            data = path.read_bytes()
            relative = path.relative_to(run_dir)
            info = tarfile.TarInfo(f"{results['run_id']}/{relative.as_posix()}")
            info.size = len(data)
            info.mode = 0o644
            info.mtime = info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    archive_path.write_bytes(zstd.ZstdCompressor(level=19).compress(buffer.getvalue()))
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_path.with_suffix(archive_path.suffix + ".sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="ascii"
    )
    return archive_path
