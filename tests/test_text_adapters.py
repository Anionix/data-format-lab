import json
from pathlib import Path

import pytest

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.formats import CsvAdapter, ObjectJsonlAdapter
from format_bench.model import Comparability, Lane


DATASET = Path("datasets/github-stars-2026-07-03")


@pytest.fixture
def fixture_contract():
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    manifest["rows"] = table.num_rows
    manifest["canonical_hash"] = canonical_hash(table)
    manifest["expected_counts"] = query_counts(table)
    return manifest, table


@pytest.mark.parametrize("adapter", [CsvAdapter(), ObjectJsonlAdapter()])
def test_text_adapter_roundtrips_equal_arrow_content(tmp_path, fixture_contract, adapter) -> None:
    manifest, table = fixture_contract
    description = adapter.describe()
    path = tmp_path / f"artifact{description.extension}"
    artifact = adapter.encode(table, path)

    assert description.lane is Lane.FAIR
    assert description.comparability is Comparability.FULL_COMPARABLE
    assert artifact.native_bytes == path.stat().st_size
    assert artifact.transport_zstd_bytes > 0
    assert adapter.verify_roundtrip(path, manifest)["passed"] is True
