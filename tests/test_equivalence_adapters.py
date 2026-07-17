from __future__ import annotations

import json
from pathlib import Path

import pytest

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.formats import FeatherV2Adapter, OrcAdapter, TsvAdapter


DATASET = Path("datasets/github-stars-2026-07-03")


@pytest.fixture
def fixture_contract() -> tuple[dict, object]:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest["rows"] = table.num_rows
    manifest["canonical_hash"] = canonical_hash(table)
    manifest["expected_counts"] = query_counts(table)
    return manifest, table


@pytest.mark.parametrize(
    "adapter", [TsvAdapter(), FeatherV2Adapter(), OrcAdapter()], ids=lambda item: item.describe().name
)
def test_text_arrow_equivalence_adapters_roundtrip(
    fixture_contract, tmp_path: Path, adapter
) -> None:
    manifest, table = fixture_contract
    description = adapter.describe()
    path = tmp_path / f"artifact{description.extension}"
    artifact = adapter.encode(table, path)

    assert artifact.native_bytes == path.stat().st_size
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True
