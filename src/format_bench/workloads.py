from __future__ import annotations

from collections.abc import Mapping

import pyarrow as pa

from .arrow_compute import equal, greater, greater_equal, less, less_equal
from .contracts import normalized_workload_entry
from .model import WorkloadKind, WorkloadSpec


_LEGACY_OPERATION_NAMES = (
    "read_all",
    "project_two",
    "filter_ai_llm",
    "filter_repo_stars_gt_100000",
    "exact_match",
    "head_10",
)


def _legacy_workloads() -> dict[str, WorkloadSpec]:
    return {
        "read_all": WorkloadSpec(
            "read_all", WorkloadKind.READ_ALL
        ),
        "project_two": WorkloadSpec(
            "project_two",
            WorkloadKind.PROJECTION,
            columns=("full_name", "repo_stars"),
        ),
        "filter_ai_llm": WorkloadSpec(
            "filter_ai_llm",
            WorkloadKind.FILTER,
            column="group",
            operator="eq",
            value="AI / LLM",
        ),
        "filter_repo_stars_gt_100000": WorkloadSpec(
            "filter_repo_stars_gt_100000",
            WorkloadKind.FILTER,
            column="repo_stars",
            operator="gt",
            value=100000,
        ),
        "exact_match": WorkloadSpec(
            "exact_match",
            WorkloadKind.FILTER,
            column="full_name",
            operator="eq",
            value="anomalyco/opencode",
        ),
        "head_10": WorkloadSpec(
            "head_10", WorkloadKind.HEAD, limit=10
        ),
    }


def load_workloads(manifest: Mapping[str, object]) -> dict[str, WorkloadSpec]:
    raw = manifest.get("workloads")
    if raw is None:
        return _legacy_workloads()
    if not isinstance(raw, Mapping):
        raise ValueError("manifest workloads must be an object")
    workloads: dict[str, WorkloadSpec] = {}
    for operation, payload in raw.items():
        operation, normalized_payload = normalized_workload_entry(operation, payload)
        workloads[operation] = WorkloadSpec.from_mapping(operation, normalized_payload)
    return workloads


def _nonnegative_int(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context} must be a non-negative integer")
    return value


def validated_expected_counts(manifest: Mapping[str, object]) -> dict[str, int]:
    raw = manifest.get("expected_counts")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or not all(isinstance(key, str) for key in raw):
        raise ValueError("manifest expected_counts must be an object with string keys")
    return {
        str(key): _nonnegative_int(value, f"expected count {key}")
        for key, value in raw.items()
    }


def _predicate(spec: WorkloadSpec, table: pa.Table) -> pa.Array | pa.ChunkedArray:
    assert spec.column is not None
    assert spec.operator is not None
    values = table[spec.column]
    comparator = {
        "eq": equal,
        "gt": greater,
        "gte": greater_equal,
        "lt": less,
        "lte": less_equal,
    }[spec.operator]
    return comparator(values, spec.value)


def apply_workload(table: pa.Table, spec: WorkloadSpec) -> pa.Table:
    if spec.kind is WorkloadKind.PROJECTION:
        return table.select(list(spec.columns))
    if spec.kind is WorkloadKind.FILTER:
        return table.filter(_predicate(spec, table))
    if spec.kind is WorkloadKind.HEAD:
        return table.slice(0, spec.limit)
    return table


def expected_workload_rows(
    operation: str, manifest: Mapping[str, object], spec: WorkloadSpec
) -> int:
    if spec.expected_rows is not None:
        return spec.expected_rows
    expected_counts = validated_expected_counts(manifest)
    if operation in expected_counts:
        return _nonnegative_int(expected_counts[operation], f"expected count {operation}")
    legacy_aliases = {
        "filter_ai_llm": "group_ai_llm",
        "filter_repo_stars_gt_100000": "repo_stars_gt_100000",
        "exact_match": "full_name_anomalyco_opencode",
    }
    alias = legacy_aliases.get(operation)
    if alias is not None and alias in expected_counts:
        return _nonnegative_int(expected_counts[alias], f"expected count {alias}")
    rows = _nonnegative_int(manifest.get("rows"), "manifest rows")
    return min(spec.limit or rows, rows) if spec.kind is WorkloadKind.HEAD else rows
