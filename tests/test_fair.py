from pathlib import Path

import pytest

from format_bench.canonical import read_csv
from format_bench.datasets import load_manifest
from format_bench.fair import OPERATIONS, apply_arrow, expected_rows, result_evidence
from format_bench.formats.lance import LanceAdapter
from format_bench.formats.parquet import ParquetAdapter
from format_bench.formats.text import CsvAdapter, ObjectJsonlAdapter
from format_bench.formats.vortex import VortexAdapter


@pytest.mark.parametrize(
    "adapter",
    [CsvAdapter(), ObjectJsonlAdapter(), ParquetAdapter(), LanceAdapter(), VortexAdapter()],
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
        assert result_evidence(actual) == result_evidence(expected)
