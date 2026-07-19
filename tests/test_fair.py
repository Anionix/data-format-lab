from pathlib import Path

import pyarrow as pa
import pytest

from format_bench.canonical import read_csv
from format_bench.datasets import load_manifest
from format_bench.fair import (
    OPERATIONS,
    FairOperation,
    apply_arrow,
    expected_rows,
    result_evidence,
)
from format_bench.formats.arrow_ipc import ArrowIpcAdapter
from format_bench.formats.lance import LanceAdapter
from format_bench.formats.parquet import ParquetAdapter
from format_bench.formats.text import CsvAdapter, ObjectJsonlAdapter
from format_bench.formats.vortex import VortexAdapter


def test_result_evidence_includes_type_and_nullability() -> None:
    nullable = pa.Table.from_arrays(
        [pa.array([1], type=pa.int64())],
        schema=pa.schema([pa.field("value", pa.int64(), nullable=True)]),
    )
    required = pa.Table.from_arrays(
        [pa.array([1], type=pa.int64())],
        schema=pa.schema([pa.field("value", pa.int64(), nullable=False)]),
    )
    assert (
        result_evidence(nullable, FairOperation.READ_ALL)["schema"]
        != result_evidence(required, FairOperation.READ_ALL)["schema"]
    )


def test_result_evidence_remains_order_insensitive() -> None:
    table = pa.table({"value": [1, 2, 3]})
    reversed_table = table.take(pa.array([2, 1, 0]))

    evidence = result_evidence(table, FairOperation.READ_ALL)
    assert evidence["row_order"] == "ORDER_INSENSITIVE"
    assert evidence == result_evidence(reversed_table, FairOperation.READ_ALL)


def test_head_result_evidence_preserves_row_order() -> None:
    table = pa.table({"value": [1, 2, 3]})
    reversed_table = table.take(pa.array([2, 1, 0]))

    evidence = result_evidence(table, FairOperation.HEAD_10)
    assert evidence["row_order"] == "ORDER_SENSITIVE"
    assert evidence != result_evidence(reversed_table, FairOperation.HEAD_10)


@pytest.mark.parametrize(
    "adapter",
    [
        CsvAdapter(),
        ObjectJsonlAdapter(),
        ArrowIpcAdapter(),
        ArrowIpcAdapter("lz4"),
        ArrowIpcAdapter("zstd"),
        ParquetAdapter(),
        ParquetAdapter(compression="snappy"),
        ParquetAdapter(compression="gzip"),
        ParquetAdapter(compression_level=19),
        LanceAdapter(),
        VortexAdapter(),
    ],
    ids=lambda adapter: adapter.describe().name,
)
def test_fair_operations_return_the_same_fixture_rows(tmp_path: Path, adapter) -> None:
    root = Path(__file__).parents[1]
    manifest = load_manifest(root, "github-stars-2026-07-03")
    source = root / "datasets" / "github-stars-2026-07-03" / "fixture.csv"
    table = read_csv(source, manifest)
    manifest = {
        **manifest,
        "rows": table.num_rows,
        "expected_counts": {
            "rows": 4,
            "group_ai_llm": 4,
            "repo_stars_gt_100000": 1,
            "full_name_anomalyco_opencode": 1,
        },
    }
    path = tmp_path / (adapter.describe().name + adapter.describe().extension)
    adapter.encode(table, path)

    for operation in OPERATIONS:
        actual = adapter.scan(path, manifest, operation)
        expected = apply_arrow(table, operation)
        assert actual.num_rows == expected_rows(operation, manifest)
        assert result_evidence(actual, operation) == result_evidence(
            expected, operation
        )
