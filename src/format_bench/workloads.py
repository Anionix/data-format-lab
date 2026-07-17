from __future__ import annotations

from collections.abc import Mapping

import pyarrow as pa
import pyarrow.compute as pc

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
    workloads = {
        str(operation): WorkloadSpec.from_mapping(str(operation), payload)
        for operation, payload in raw.items()
        if isinstance(payload, Mapping)
    }
    if len(workloads) != len(raw):
        raise ValueError("each workload must be an object")
    return workloads


def _predicate(spec: WorkloadSpec, table: pa.Table) -> pa.Array:
    assert spec.column is not None
    assert spec.operator is not None
    values = table[spec.column]
    comparator = {
        "eq": pc.equal,
        "gt": pc.greater,
        "gte": pc.greater_equal,
        "lt": pc.less,
        "lte": pc.less_equal,
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
    expected_counts = manifest.get("expected_counts", {})
    if isinstance(expected_counts, Mapping) and operation in expected_counts:
        return int(expected_counts[operation])
    legacy_aliases = {
        "filter_ai_llm": "group_ai_llm",
        "filter_repo_stars_gt_100000": "repo_stars_gt_100000",
        "exact_match": "full_name_anomalyco_opencode",
    }
    alias = legacy_aliases.get(operation)
    if isinstance(expected_counts, Mapping) and alias in expected_counts:
        return int(expected_counts[alias])
    rows = int(manifest["rows"])
    return min(spec.limit or rows, rows) if spec.kind is WorkloadKind.HEAD else rows
