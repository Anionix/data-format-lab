import copy
import json
from pathlib import Path

import pyarrow as pa
import pytest

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.model import ObservedOutcome
from format_bench.robustness import (
    core_targets,
    encode_malformed,
    encode_valid,
    materialize_case,
    named_cases,
    target_map,
)
from format_bench.robustness.worker import run_request


DATASET = Path("datasets/github-stars-2026-07-03")


def _fixture() -> tuple[dict, pa.Table]:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    fixture = copy.deepcopy(manifest)
    fixture["rows"] = table.num_rows
    fixture["canonical_hash"] = ""
    return fixture, table


def test_core_targets_reuse_registered_adapters() -> None:
    assert [target.name for target in core_targets()] == [
        "csv",
        "object_jsonl",
        "parquet_default",
        "parquet_zstd19",
        "lance_base",
        "vortex_default",
        "vortex_compact",
    ]
    assert set(target_map()) == {target.name for target in core_targets()}


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
def test_valid_boundary_cases_round_trip_through_each_core_target(tmp_path: Path, target) -> None:
    manifest, base = _fixture()
    cases = {case.case_id: case for case in named_cases()}
    table = materialize_case(base, cases["rows-1024"])
    path = tmp_path / f"valid{target.adapter.describe().extension}"
    encode_valid(target, table, path)
    case_manifest = {
        **manifest,
        "rows": 1024,
        "canonical_hash": canonical_hash(table),
        "expected_counts": query_counts(table),
    }
    assert target.adapter.verify_roundtrip(path, case_manifest)["passed"] is True


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
@pytest.mark.parametrize("kind", ["missing_column", "extra_column"])
def test_column_shape_cases_are_constructed_for_each_core_target(tmp_path: Path, target, kind: str) -> None:
    _, base = _fixture()
    path = tmp_path / f"malformed{target.adapter.describe().extension}"
    artifact = encode_malformed(target, base, path, kind)
    assert path.exists()
    if path.is_file():
        assert path.stat().st_size > 0
        assert artifact.native_bytes == path.stat().st_size
    else:
        assert artifact.native_bytes > 0


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
def test_malformed_constructor_rejects_unknown_cases(tmp_path: Path, target) -> None:
    _, base = _fixture()
    with pytest.raises(ValueError, match="unsupported"):
        encode_malformed(target, base, tmp_path / f"bad{target.adapter.describe().extension}", "truncated")


@pytest.mark.parametrize("target", core_targets(), ids=lambda item: item.name)
@pytest.mark.parametrize("kind", ["missing_column", "extra_column"])
def test_malformed_column_cases_are_rejected_by_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target, kind: str
) -> None:
    manifest, base = _fixture()
    manifest["canonical_hash"] = canonical_hash(base)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.chdir(tmp_path)
    path = tmp_path / f"malformed{target.adapter.describe().extension}"
    encode_malformed(target, base, path, kind)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "schema_version": "1",
        "case_id": f"{target.name}-{kind}",
        "target": target.name,
        "expectation": "MUST_REJECT",
        "manifest": "manifest.json",
        "artifact": path.name,
    }))
    result = run_request(request)
    assert result["observed"] is ObservedOutcome.REJECTED
