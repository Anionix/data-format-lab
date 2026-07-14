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


def _safe_slug(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ValueError("platform must be a lowercase release slug")
    return value


def package_run(run_dir: Path, output: Path, platform: str) -> Path:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    if manifest["state"] != ExecutionState.BENCHMARKED:
        raise ValueError("release packaging requires benchmarked evidence")
    if results["state"] != ExecutionState.BENCHMARKED:
        raise ValueError("release packaging requires benchmarked results")
    if manifest["dataset_id"] != results["dataset_id"]:
        raise ValueError("release manifest and results dataset mismatch")

    files = [run_dir / relative for relative in EVIDENCE_FILES]
    missing = [str(path.relative_to(run_dir)) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"release evidence missing: {', '.join(missing)}")

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
