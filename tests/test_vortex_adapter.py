import json
from pathlib import Path

import pytest

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.claims import run_vortex_stress
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


def test_vortex_stress_keeps_results_equal(tmp_path: Path, fixture_contract) -> None:
    _, table = fixture_contract
    result = run_vortex_stress(table, tmp_path, rows=8, warmups=0, iterations=1)
    for variant in ("sorted", "unsorted"):
        for operation in result[variant]["operations"].values():
            assert operation["parquet"]["result"] == operation["vortex"]["result"]
