import hashlib
import json
import tarfile
from pathlib import Path

import zstandard as zstd

from format_bench.release import package_run


def test_release_package_is_deterministic_and_relative(tmp_path: Path) -> None:
    run = tmp_path / "run"
    (run / "input").mkdir(parents=True)
    manifest = {
        "state": "REPORTED",
        "dataset_id": "fixture",
        "formats": [{"artifact": "artifacts/value.bin"}],
    }
    results = {
        "state": "REPORTED",
        "dataset_id": "fixture",
        "profile": "fair",
        "run_id": "run-1",
        "results": {
            "negative_research": {
                "source_commits": {"artifact": "not-a-run-path"}
            }
        },
    }
    payloads = {
        "manifest.json": json.dumps(manifest),
        "results.json": json.dumps(results),
        "report.md": "# report\n",
        "input/manifest.json": '{"dataset_id":"fixture"}\n',
    }
    for relative, payload in payloads.items():
        (run / relative).write_text(payload)
    (run / "artifacts").mkdir()
    (run / "artifacts" / "value.bin").write_bytes(b"artifact")
    (run / "claims" / "nested").mkdir(parents=True)
    (run / "claims" / "nested" / "evidence.bin").write_bytes(b"claim")

    first = package_run(run, tmp_path / "first", "linux-x86_64")
    second = package_run(run, tmp_path / "second", "linux-x86_64")
    assert first.read_bytes() == second.read_bytes()
    digest = hashlib.sha256(first.read_bytes()).hexdigest()
    assert first.with_suffix(".zst.sha256").read_text() == f"{digest}  {first.name}\n"

    tar_bytes = zstd.ZstdDecompressor().decompress(first.read_bytes())
    with tarfile.open(fileobj=__import__("io").BytesIO(tar_bytes)) as archive:
        assert archive.getnames() == [
            "run-1/artifacts/value.bin",
            "run-1/claims/nested/evidence.bin",
            "run-1/input/manifest.json",
            "run-1/manifest.json",
            "run-1/report.md",
            "run-1/results.json",
        ]
        assert all(not Path(name).is_absolute() for name in archive.getnames())


def test_release_rejects_missing_referenced_artifact(tmp_path: Path) -> None:
    run = tmp_path / "run"
    (run / "input").mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "state": "REPORTED",
                "dataset_id": "fixture",
                "formats": [{"artifact": "artifacts/missing.bin"}],
            }
        )
    )
    (run / "results.json").write_text(
        json.dumps(
            {
                "state": "REPORTED",
                "dataset_id": "fixture",
                "profile": "fair",
                "run_id": "run-1",
            }
        )
    )
    (run / "report.md").write_text("# report\n")
    (run / "input" / "manifest.json").write_text('{}\n')

    try:
        package_run(run, tmp_path / "output", "linux-x86_64")
    except FileNotFoundError as error:
        assert "artifacts/missing.bin" in str(error)
    else:
        raise AssertionError("missing artifact was accepted")
