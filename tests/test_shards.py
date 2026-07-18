from __future__ import annotations

import json
from pathlib import Path

from format_bench.shards import merge_equivalence_shards


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _manifest() -> dict:
    return {
        "dataset_id": "fixture",
        "state": "ROUNDTRIP_VERIFIED",
        "input": {"manifest": "input/manifest.json"},
        "formats": [
            {"format": "arrow_ipc", "state": "ROUNDTRIP_VERIFIED"},
            {"format": "feather_v2", "state": "ROUNDTRIP_VERIFIED"},
        ],
    }


def _shard_results(pair: str, name: str) -> dict:
    return {
        "dataset_id": "fixture",
        "environment": {"platform": "test"},
        "measurement": {"fresh_processes": 10, "warmups": 5, "iterations": 30},
        "state": "BENCHMARKED",
        "status": "MEASURED",
        "results": {f"{name}/read_all": {"status": "MEASURED", "result": 4}},
        "equivalence": {
            "bounds": {"size_ratio": 0.02},
            "pairs": {pair: {"verdict": "PRACTICALLY_EQUIVALENT"}},
        },
    }


def test_merge_equivalence_shards_reuses_artifacts_and_unions_results(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    _write(base / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(base / "manifest.json", _manifest())

    shard_root = tmp_path / "shards"
    for pair, name in (("arrow-feather", "arrow_ipc"), ("csv-tsv", "feather_v2")):
        shard = shard_root / pair
        _write(shard / "manifest.json", {"dataset_id": "fixture", "state": "BENCHMARKED"})
        _write(shard / "results.json", _shard_results(pair, name))

    output = tmp_path / "merged"
    merge_equivalence_shards(base, shard_root, output)

    merged = json.loads((output / "results.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert merged["status"] == "MEASURED"
    assert set(merged["results"]) == {"arrow_ipc/read_all", "feather_v2/read_all"}
    assert set(merged["equivalence"]["pairs"]) == {"arrow-feather", "csv-tsv"}
    assert manifest["state"] == "BENCHMARKED"
    assert not any(path.is_symlink() for path in output.rglob("*"))
