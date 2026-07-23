import json
from pathlib import Path

import pyarrow as pa
import pytest

import format_bench.claims.vortex as vortex_claim
from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.claims import run_vortex_stress
from format_bench.fair import FairOperation, result_evidence
from format_bench.formats import VortexAdapter


DATASET = Path("datasets/github-stars-2026-07-03")


@pytest.fixture
def fixture_contract():
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest["rows"] = table.num_rows
    manifest["canonical_hash"] = canonical_hash(table)
    manifest["expected_counts"] = query_counts(table)
    return manifest, table


@pytest.mark.parametrize("compact", [False, True])
def test_vortex_variants_roundtrip(tmp_path: Path, fixture_contract, compact: bool) -> None:
    manifest, table = fixture_contract
    adapter = VortexAdapter(compact)
    path = tmp_path / f"{adapter.describe().name}.vortex"
    adapter.encode(table, path)
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True


def test_vortex_stress_keeps_results_equal(
    tmp_path: Path, fixture_contract, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, table = fixture_contract
    real_open = vortex_claim.vortex.open
    open_count = 0

    def tracked_open(path: str):
        nonlocal open_count
        open_count += 1
        return real_open(path)

    monkeypatch.setattr(vortex_claim.vortex, "open", tracked_open)
    result = run_vortex_stress(table, tmp_path, rows=8, warmups=0, iterations=1)
    for variant in ("sorted", "unsorted"):
        for operation in result[variant]["operations"].values():
            assert operation["parquet"]["result"] == operation["vortex"]["result"]
            assert operation["parquet"]["evidence"] == operation["vortex"]["evidence"]
    assert open_count == 8


def test_vortex_stress_rejects_equal_counts_with_different_values(
    tmp_path: Path, fixture_contract, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, table = fixture_contract
    original = result_evidence(pa.table({"value": [1]}), FairOperation.READ_ALL)
    changed = result_evidence(pa.table({"value": [2]}), FairOperation.READ_ALL)
    measurements = iter(
        [
            {"result": 1, "evidence": original},
            {"result": 1, "evidence": changed},
        ]
    )
    monkeypatch.setattr(vortex_claim, "_measure", lambda *_: next(measurements))

    with pytest.raises(ValueError, match="stress result mismatch"):
        run_vortex_stress(table, tmp_path, rows=8, warmups=0, iterations=1)
