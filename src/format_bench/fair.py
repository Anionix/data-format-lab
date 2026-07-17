from __future__ import annotations

from enum import StrEnum

import pyarrow as pa
import pyarrow.dataset as ds

from .canonical import canonical_hash
from .workloads import apply_workload, expected_workload_rows, load_workloads


class FairOperation(StrEnum):
    READ_ALL = "read_all"
    PROJECT_TWO = "project_two"
    FILTER_AI_LLM = "filter_ai_llm"
    FILTER_POPULAR = "filter_repo_stars_gt_100000"
    EXACT_MATCH = "exact_match"
    HEAD_10 = "head_10"


OPERATIONS = tuple(FairOperation)


def columns_for(operation: FairOperation) -> list[str] | None:
    spec = load_workloads({})[operation.value]
    return list(spec.columns) if spec.columns else None


def arrow_filter(operation: FairOperation):
    if operation is FairOperation.FILTER_AI_LLM:
        return ds.field("group") == "AI / LLM"
    if operation is FairOperation.FILTER_POPULAR:
        return ds.field("repo_stars") > 100000
    if operation is FairOperation.EXACT_MATCH:
        return ds.field("full_name") == "anomalyco/opencode"
    return None


def lance_filter(operation: FairOperation) -> str | None:
    if operation is FairOperation.FILTER_AI_LLM:
        return "group = 'AI / LLM'"
    if operation is FairOperation.FILTER_POPULAR:
        return "repo_stars > 100000"
    if operation is FairOperation.EXACT_MATCH:
        return "full_name = 'anomalyco/opencode'"
    return None


def limit_for(operation: FairOperation, rows: int) -> int | None:
    return min(10, rows) if operation is FairOperation.HEAD_10 else None


def apply_arrow(table: pa.Table, operation: FairOperation) -> pa.Table:
    return apply_workload(table, load_workloads({})[operation.value])


def expected_rows(operation: FairOperation, manifest: dict) -> int:
    workloads = load_workloads(manifest)
    spec = workloads[operation.value]
    return expected_workload_rows(operation.value, manifest, spec)


def result_evidence(table: pa.Table) -> dict:
    return {
        "rows": table.num_rows,
        "columns": table.column_names,
        "schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in table.schema
        ],
        "normalized_hash": canonical_hash(table),
    }
