import hashlib
import json
import tarfile
from pathlib import Path

import zstandard as zstd

from format_bench.release import EVIDENCE_FILES, package_run


def test_release_package_is_deterministic_and_relative(tmp_path: Path) -> None:
    run = tmp_path / "run"
    (run / "input").mkdir(parents=True)
    manifest = {"state": "REPORTED", "dataset_id": "fixture"}
    results = {
        "state": "REPORTED",
        "dataset_id": "fixture",
        "profile": "fair",
        "run_id": "run-1",
    }
    payloads = {
        "manifest.json": json.dumps(manifest),
        "results.json": json.dumps(results),
        "report.md": "# report\n",
        "input/manifest.json": '{"dataset_id":"fixture"}\n',
    }
    for relative, payload in payloads.items():
        (run / relative).write_text(payload)

    first = package_run(run, tmp_path / "first", "linux-x86_64")
    second = package_run(run, tmp_path / "second", "linux-x86_64")
    assert first.read_bytes() == second.read_bytes()
    digest = hashlib.sha256(first.read_bytes()).hexdigest()
    assert first.with_suffix(".zst.sha256").read_text() == f"{digest}  {first.name}\n"

    tar_bytes = zstd.ZstdDecompressor().decompress(first.read_bytes())
    with tarfile.open(fileobj=__import__("io").BytesIO(tar_bytes)) as archive:
        assert archive.getnames() == [f"run-1/{name}" for name in EVIDENCE_FILES]
        assert all(not Path(name).is_absolute() for name in archive.getnames())
