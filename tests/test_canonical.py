import copy
import json
from pathlib import Path

import pyarrow as pa
import pytest

from format_bench.canonical import (
    arrow_schema,
    canonical_hash,
    query_counts,
    read_csv,
    verify_table,
)


DATASET = Path("datasets/github-stars-2026-07-03")


def fixture_contract() -> tuple[dict, pa.Table]:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    table = read_csv(DATASET / "fixture.csv", manifest)
    fixture = copy.deepcopy(manifest)
    fixture["rows"] = table.num_rows
    fixture["canonical_hash"] = canonical_hash(table)
    fixture["expected_counts"] = query_counts(table)
    return fixture, table


def test_fixture_uses_the_declared_arrow_schema_and_nulls() -> None:
    manifest, table = fixture_contract()
    assert table.schema == arrow_schema(manifest)
    assert table.num_rows == 4
    assert table["topics"].null_count == 2


def test_canonical_hash_is_independent_of_row_order() -> None:
    _, table = fixture_contract()
    assert canonical_hash(table) == canonical_hash(table.take(pa.array([3, 2, 1, 0])))


def test_verify_table_checks_hash_schema_rows_and_queries() -> None:
    manifest, table = fixture_contract()
    assert verify_table(table, manifest)["passed"] is True

    wrong_hash = {**manifest, "canonical_hash": "0" * 64}
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        verify_table(table, wrong_hash)

    wrong_rows = {**manifest, "rows": 5}
    with pytest.raises(ValueError, match="row count mismatch"):
        verify_table(table, wrong_rows)
