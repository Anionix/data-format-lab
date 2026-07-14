from __future__ import annotations

from enum import StrEnum

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

from .canonical import canonical_hash


class FairOperation(StrEnum):
    READ_ALL = "read_all"
    PROJECT_TWO = "project_two"
    FILTER_AI_LLM = "filter_ai_llm"
    FILTER_POPULAR = "filter_repo_stars_gt_100000"
    EXACT_MATCH = "exact_match"
    HEAD_10 = "head_10"


OPERATIONS = tuple(FairOperation)


def columns_for(operation: FairOperation) -> list[str] | None:
    return ["full_name", "repo_stars"] if operation is FairOperation.PROJECT_TWO else None


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
    if operation is FairOperation.PROJECT_TWO:
        return table.select(columns_for(operation))
    if operation is FairOperation.FILTER_AI_LLM:
        return table.filter(pc.equal(table["group"], "AI / LLM"))
    if operation is FairOperation.FILTER_POPULAR:
        return table.filter(pc.greater(table["repo_stars"], 100000))
    if operation is FairOperation.EXACT_MATCH:
        return table.filter(pc.equal(table["full_name"], "anomalyco/opencode"))
    if operation is FairOperation.HEAD_10:
        return table.slice(0, 10)
    return table


def expected_rows(operation: FairOperation, manifest: dict) -> int:
    counts = manifest["expected_counts"]
    expected = {
        FairOperation.FILTER_AI_LLM: counts["group_ai_llm"],
        FairOperation.FILTER_POPULAR: counts["repo_stars_gt_100000"],
        FairOperation.EXACT_MATCH: counts["full_name_anomalyco_opencode"],
        FairOperation.HEAD_10: min(10, manifest["rows"]),
    }
    return expected.get(operation, manifest["rows"])


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
