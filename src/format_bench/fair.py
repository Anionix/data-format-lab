from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

import pyarrow as pa
import pyarrow.dataset as ds

from .canonical import order_insensitive_hash
from .workloads import apply_workload, expected_workload_rows, load_workloads


class FairOperation(StrEnum):
    READ_ALL = "read_all"
    PROJECT_TWO = "project_two"
    FILTER_AI_LLM = "filter_ai_llm"
    FILTER_POPULAR = "filter_repo_stars_gt_100000"
    EXACT_MATCH = "exact_match"
    HEAD_10 = "head_10"


OPERATIONS = tuple(FairOperation)
Operation = FairOperation | str


def operations_for(manifest: Mapping[str, object] | None = None) -> tuple[str, ...]:
    if manifest is not None and "workloads" in manifest:
        workloads = load_workloads(manifest)
        return tuple(workloads)
    return tuple(operation.value for operation in OPERATIONS)


def _operation_name(operation: Operation) -> str:
    return operation.value if isinstance(operation, FairOperation) else operation


def workload_for(
    operation: Operation, manifest: Mapping[str, object] | None = None
):
    return load_workloads(manifest or {})[_operation_name(operation)]


def columns_for(
    operation: Operation, manifest: Mapping[str, object] | None = None
) -> list[str] | None:
    spec = workload_for(operation, manifest)
    return list(spec.columns) if spec.columns else None


def arrow_filter(
    operation: Operation, manifest: Mapping[str, object] | None = None
):
    spec = workload_for(operation, manifest)
    if spec.kind.value != "filter":
        return None
    field = ds.field(spec.column)
    if spec.operator == "eq":
        return field == spec.value
    if spec.operator == "gt":
        return field > spec.value
    if spec.operator == "gte":
        return field >= spec.value
    if spec.operator == "lt":
        return field < spec.value
    return field <= spec.value


def lance_filter(
    operation: Operation, manifest: Mapping[str, object] | None = None
) -> str | None:
    spec = workload_for(operation, manifest)
    if spec.kind.value != "filter":
        return None
    if isinstance(spec.value, str):
        value = "'" + spec.value.replace("'", "''") + "'"
    else:
        value = str(spec.value)
    operator = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[spec.operator]
    return f"{spec.column} {operator} {value}"


def limit_for(
    operation: Operation,
    rows: int,
    manifest: Mapping[str, object] | None = None,
) -> int | None:
    spec = workload_for(operation, manifest)
    return min(spec.limit, rows) if spec.kind.value == "head" else None


def apply_arrow(
    table: pa.Table,
    operation: Operation,
    manifest: Mapping[str, object] | None = None,
) -> pa.Table:
    return apply_workload(table, workload_for(operation, manifest))


def expected_rows(operation: Operation, manifest: dict) -> int:
    workloads = load_workloads(manifest)
    name = _operation_name(operation)
    spec = workloads[name]
    return expected_workload_rows(name, manifest, spec)


def result_evidence(table: pa.Table) -> dict:
    return {
        "rows": table.num_rows,
        "columns": table.column_names,
        "schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in table.schema
        ],
        "normalized_hash": order_insensitive_hash(table),
    }
