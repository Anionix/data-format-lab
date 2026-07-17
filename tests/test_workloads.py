from __future__ import annotations

import pyarrow as pa
import pytest

from format_bench.fair import FairOperation, operations_for
from format_bench.workloads import apply_workload, expected_workload_rows, load_workloads


def test_manifest_workload_is_not_tied_to_stars_columns() -> None:
    manifest = {
        "rows": 3,
        "workloads": {
            "read_all": {"kind": "read_all", "expected_rows": 3},
            "project_two": {"kind": "projection", "columns": ["name", "amount"]},
            "filter_ai_llm": {
                "kind": "filter",
                "column": "name",
                "operator": "eq",
                "value": "b",
                "expected_rows": 1,
            },
            "filter_repo_stars_gt_100000": {
                "kind": "filter",
                "column": "amount",
                "operator": "gt",
                "value": 10,
                "expected_rows": 2,
            },
            "exact_match": {
                "kind": "filter",
                "column": "name",
                "operator": "eq",
                "value": "c",
                "expected_rows": 1,
            },
            "head_10": {"kind": "head", "limit": 10},
        },
    }
    table = pa.table({"name": ["a", "b", "c"], "amount": [1, 11, 21]})
    workloads = load_workloads(manifest)
    for operation in FairOperation:
        result = apply_workload(table, workloads[operation.value])
        assert result.num_rows == expected_workload_rows(
            operation.value, manifest, workloads[operation.value]
        )


def test_manifest_rejects_non_object_workloads() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        load_workloads({"workloads": []})


def test_operations_for_uses_dataset_declared_names() -> None:
    manifest = {
        "workloads": {
            "read_all": {"kind": "read_all"},
            "filter_custom": {
                "kind": "filter",
                "column": "name",
                "operator": "eq",
                "value": "a",
            },
        }
    }
    assert operations_for(manifest) == ("read_all", "filter_custom")
    assert operations_for({}) == tuple(operation.value for operation in FairOperation)
