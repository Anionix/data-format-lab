from __future__ import annotations

import json
from pathlib import Path

import pytest

from format_bench.shards import merge_equivalence_shards


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _manifest() -> dict:
    return {
        "dataset_id": "fixture",
        "state": "ROUNDTRIP_VERIFIED",
        "input": {
            "manifest": "input/manifest.json",
            "source": "input/source.csv",
        },
        "formats": [
            {
                "format": "arrow_ipc",
                "artifact": "artifacts/arrow.arrow",
                "lane": "fair",
                "comparability": "FULL_COMPARABLE",
                "settings": {},
                "state": "ROUNDTRIP_VERIFIED",
            },
            {
                "format": "feather_v2",
                "artifact": "artifacts/feather.feather",
                "lane": "equivalence",
                "comparability": "FULL_COMPARABLE",
                "settings": {},
                "state": "ROUNDTRIP_VERIFIED",
            },
            {
                "format": "tsfile",
                "artifact": "artifacts/tsfile.tsfile",
                "lane": "claims",
                "comparability": "ADAPTED",
                "settings": {},
                "state": "UNSUPPORTED",
                "failure_reason": "optional dependency unavailable",
            },
        ],
    }


def _shard_results(pair: str, name: str) -> dict:
    return {
        "dataset_id": "fixture",
        "environment": {"platform": "test"},
        "measurement": {"fresh_processes": 10, "warmups": 5, "iterations": 30},
        "profile": "equivalence",
        "state": "BENCHMARKED",
        "status": "MEASURED",
        "results": {f"{name}/read_all": {"status": "MEASURED", "result": 4}},
        "equivalence": {
            "contract_version": "2",
            "bounds": {"size_ratio": 0.02},
            "primary_endpoints": {
                pair: {"scope": "storage", "metric": "native_bytes"}
            },
            "pairs": {
                pair: {
                    "primary_endpoint": {
                        "scope": "storage",
                        "metric": "native_bytes",
                    },
                    "verdict_basis": "primary_endpoint",
                    "verdict": "PRACTICALLY_EQUIVALENT",
                }
            },
        },
    }


def test_merge_equivalence_shards_reuses_artifacts_and_unions_results(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(base / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(base / "artifacts" / "feather.feather", {"format": "feather"})
    _write(base / "manifest.json", _manifest())

    shard_root = tmp_path / "shards"
    for pair, name in (("arrow-feather", "arrow_ipc"), ("csv-tsv", "feather_v2")):
        shard = shard_root / pair
        shard_manifest = _manifest()
        shard_manifest["state"] = "BENCHMARKED"
        _write(shard / "input" / "manifest.json", {"rows": 4})
        (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
        _write(shard / "artifacts" / "arrow.arrow", {"format": "arrow"})
        _write(shard / "artifacts" / "feather.feather", {"format": "feather"})
        _write(shard / "manifest.json", shard_manifest)
        _write(shard / "results.json", _shard_results(pair, name))

    output = tmp_path / "merged"
    merge_equivalence_shards(base, shard_root, output)

    merged = json.loads((output / "results.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert merged["status"] == "MEASURED"
    assert set(merged["results"]) == {"arrow_ipc/read_all", "feather_v2/read_all"}
    assert set(merged["equivalence"]["pairs"]) == {"arrow-feather", "csv-tsv"}
    assert set(merged["equivalence"]["primary_endpoints"]) == {
        "arrow-feather",
        "csv-tsv",
    }
    assert manifest["state"] == "BENCHMARKED"
    assert not any(path.is_symlink() for path in output.rglob("*"))


@pytest.mark.parametrize("state", ["BENCHMARKED", "REPORTED"])
def test_merge_equivalence_shards_normalizes_artifact_format_state(
    tmp_path: Path, state: str
) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(base / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(base / "artifacts" / "feather.feather", {"format": "feather"})
    _write(base / "manifest.json", _manifest())

    shard = tmp_path / "shards" / "arrow-feather"
    shard_manifest = _manifest()
    shard_manifest["state"] = state
    for entry in shard_manifest["formats"]:
        if entry["state"] not in {"FAILED", "UNSUPPORTED"}:
            entry["state"] = state
    _write(shard / "input" / "manifest.json", {"rows": 4})
    (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(shard / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(shard / "artifacts" / "feather.feather", {"format": "feather"})
    _write(shard / "manifest.json", shard_manifest)
    shard_results = _shard_results("arrow-feather", "arrow_ipc")
    shard_results["state"] = state
    _write(shard / "results.json", shard_results)

    merge_equivalence_shards(base, tmp_path / "shards", tmp_path / "merged")


@pytest.mark.parametrize("state", ["DISCOVERED", "ENCODED"])
def test_merge_equivalence_shards_rejects_preverification_format_state(
    tmp_path: Path, state: str
) -> None:
    base = tmp_path / "base"
    shard = tmp_path / "shards" / "arrow-feather"
    for run in (base, shard):
        _write(run / "input" / "manifest.json", {"rows": 4})
        (run / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
        _write(run / "artifacts" / "arrow.arrow", {"format": "arrow"})
        _write(run / "artifacts" / "feather.feather", {"format": "feather"})
    _write(base / "manifest.json", _manifest())
    shard_manifest = _manifest()
    shard_manifest["state"] = "BENCHMARKED"
    shard_manifest["formats"][0]["state"] = state
    _write(shard / "manifest.json", shard_manifest)
    _write(shard / "results.json", _shard_results("arrow-feather", "arrow_ipc"))

    with pytest.raises(ValueError, match="not verified for shard identity"):
        merge_equivalence_shards(base, tmp_path / "shards", tmp_path / "merged")


def test_merge_equivalence_shards_preserves_failed_evidence_without_artifact(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(base / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(base / "artifacts" / "feather.feather", {"format": "feather"})
    base_manifest = _manifest()
    failed_entry = base_manifest["formats"][2]
    failed_entry["state"] = "FAILED"
    failed_entry["failure_reason"] = "adapter failed before writing artifact"
    _write(base / "manifest.json", base_manifest)

    shard = tmp_path / "shards" / "failed"
    shard_manifest = _manifest()
    shard_manifest["state"] = "BENCHMARKED"
    shard_failed_entry = shard_manifest["formats"][2]
    shard_failed_entry["state"] = "FAILED"
    shard_failed_entry["failure_reason"] = failed_entry["failure_reason"]
    _write(shard / "input" / "manifest.json", {"rows": 4})
    (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(shard / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(shard / "artifacts" / "feather.feather", {"format": "feather"})
    _write(shard / "manifest.json", shard_manifest)
    _write(shard / "results.json", _shard_results("arrow-feather", "arrow_ipc"))

    output = tmp_path / "merged"
    merge_equivalence_shards(base, tmp_path / "shards", output)

    merged_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    merged_failed_entry = next(
        entry for entry in merged_manifest["formats"] if entry["format"] == "tsfile"
    )
    assert merged_failed_entry["state"] == "FAILED"
    assert merged_failed_entry["failure_reason"] == failed_entry["failure_reason"]
    assert not (output / failed_entry["artifact"]).exists()


def test_merge_equivalence_shards_rejects_terminal_format_benchmark(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(base / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(base / "artifacts" / "feather.feather", {"format": "feather"})
    base_manifest = _manifest()
    base_manifest["formats"][2]["state"] = "FAILED"
    base_manifest["formats"][2]["failure_reason"] = "adapter failed"
    _write(base / "manifest.json", base_manifest)

    shard = tmp_path / "shards" / "failed"
    shard_manifest = _manifest()
    shard_manifest["state"] = "BENCHMARKED"
    shard_manifest["formats"][2]["state"] = "FAILED"
    shard_manifest["formats"][2]["failure_reason"] = "adapter failed"
    _write(shard / "input" / "manifest.json", {"rows": 4})
    (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(shard / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(shard / "artifacts" / "feather.feather", {"format": "feather"})
    _write(shard / "manifest.json", shard_manifest)
    _write(shard / "results.json", _shard_results("arrow-feather", "tsfile"))

    with pytest.raises(ValueError, match="terminal format has benchmark job"):
        merge_equivalence_shards(base, tmp_path / "shards", tmp_path / "merged")


@pytest.mark.parametrize("identity_field", ["state", "failure_reason"])
def test_merge_equivalence_shards_rejects_terminal_identity_mismatch(
    tmp_path: Path, identity_field: str
) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(base / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(base / "artifacts" / "feather.feather", {"format": "feather"})
    base_manifest = _manifest()
    base_manifest["formats"][2]["state"] = "FAILED"
    base_manifest["formats"][2]["failure_reason"] = "adapter failed"
    _write(base / "manifest.json", base_manifest)

    shard = tmp_path / "shards" / "mismatch"
    shard_manifest = _manifest()
    shard_manifest["state"] = "BENCHMARKED"
    shard_manifest["formats"][2]["state"] = "FAILED"
    shard_manifest["formats"][2]["failure_reason"] = "adapter failed"
    if identity_field == "state":
        shard_manifest["formats"][2]["state"] = "UNSUPPORTED"
    else:
        shard_manifest["formats"][2]["failure_reason"] = "different failure"
    _write(shard / "input" / "manifest.json", {"rows": 4})
    (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(shard / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(shard / "artifacts" / "feather.feather", {"format": "feather"})
    _write(shard / "manifest.json", shard_manifest)
    _write(shard / "results.json", _shard_results("arrow-feather", "arrow_ipc"))

    with pytest.raises(ValueError, match="format artifact identity mismatch"):
        merge_equivalence_shards(base, tmp_path / "shards", tmp_path / "merged")


@pytest.mark.parametrize("missing_evidence", ["profile", "empty_profile", "pairs"])
def test_merge_equivalence_shards_requires_equivalence_evidence(
    tmp_path: Path, missing_evidence: str
) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(base / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(base / "artifacts" / "feather.feather", {"format": "feather"})
    _write(base / "manifest.json", _manifest())

    shard = tmp_path / "shards" / "arrow-feather"
    _write(shard / "input" / "manifest.json", {"rows": 4})
    (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    _write(shard / "artifacts" / "arrow.arrow", {"format": "arrow"})
    _write(shard / "artifacts" / "feather.feather", {"format": "feather"})
    _write(shard / "manifest.json", {**_manifest(), "state": "BENCHMARKED"})
    results = _shard_results("arrow-feather", "arrow_ipc")
    if missing_evidence == "profile":
        results.pop("profile")
    elif missing_evidence == "empty_profile":
        results["profile"] = ""
    else:
        results["equivalence"]["pairs"] = {}
    _write(shard / "results.json", results)

    with pytest.raises(ValueError, match="equivalence"):
        merge_equivalence_shards(base, tmp_path / "shards", tmp_path / "merged")


def test_merge_equivalence_shards_hashes_directory_artifacts(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    (base / "artifacts" / "lance.lance" / "_versions").mkdir(parents=True)
    (base / "artifacts" / "lance.lance" / "data.bin").write_bytes(b"data")
    (base / "artifacts" / "lance.lance" / "_versions" / "v1").write_text(
        "version", encoding="utf-8"
    )
    manifest = _manifest()
    manifest["formats"][0]["format"] = "lance_base"
    manifest["formats"][0]["artifact"] = "artifacts/lance.lance"
    manifest["formats"] = [manifest["formats"][0]]
    _write(base / "manifest.json", manifest)

    shard = tmp_path / "shards" / "lance"
    shard_manifest = dict(manifest)
    shard_manifest["state"] = "BENCHMARKED"
    _write(shard / "input" / "manifest.json", {"rows": 4})
    (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    (shard / "artifacts" / "lance.lance" / "_versions").mkdir(parents=True)
    (shard / "artifacts" / "lance.lance" / "data.bin").write_bytes(b"data")
    (shard / "artifacts" / "lance.lance" / "_versions" / "v1").write_text(
        "version", encoding="utf-8"
    )
    _write(shard / "manifest.json", shard_manifest)
    _write(shard / "results.json", _shard_results("lance", "lance_base"))

    merge_equivalence_shards(base, tmp_path / "shards", tmp_path / "merged")


def test_merge_equivalence_shards_rejects_artifact_kind_mismatch(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _write(base / "input" / "manifest.json", {"rows": 4})
    (base / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    (base / "artifacts" / "lance.lance").mkdir(parents=True)
    (base / "artifacts" / "lance.lance" / "data.bin").write_bytes(b"x")
    manifest = _manifest()
    manifest["formats"] = [manifest["formats"][0]]
    manifest["formats"][0]["format"] = "lance_base"
    manifest["formats"][0]["artifact"] = "artifacts/lance.lance"
    _write(base / "manifest.json", manifest)

    shard = tmp_path / "shards" / "lance"
    shard_manifest = dict(manifest)
    shard_manifest["state"] = "BENCHMARKED"
    _write(shard / "input" / "manifest.json", {"rows": 4})
    (shard / "input" / "source.csv").write_text("id\n1\n", encoding="utf-8")
    (shard / "artifacts").mkdir(parents=True)
    (shard / "artifacts" / "lance.lance").write_bytes(b"x")
    _write(shard / "manifest.json", shard_manifest)
    _write(shard / "results.json", _shard_results("lance", "lance_base"))

    try:
        merge_equivalence_shards(base, tmp_path / "shards", tmp_path / "merged")
    except ValueError as error:
        assert "artifact identity mismatch" in str(error)
    else:
        raise AssertionError("artifact kind mismatch was accepted")
