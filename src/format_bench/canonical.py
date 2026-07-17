from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from .datasets import load_manifest, sha256_bytes
from .workloads import apply_workload, load_workloads


_ARROW_TYPES = {
    "string": pa.string(),
    "float64": pa.float64(),
    "int64": pa.int64(),
    "bool": pa.bool_(),
}


def arrow_schema(manifest: dict) -> pa.Schema:
    return pa.schema(
        pa.field(
            column["name"],
            _ARROW_TYPES[column["arrow_type"]],
            nullable=column.get("nullable", True),
        )
        for column in manifest["columns"]
    )


def read_csv(path: Path, manifest: dict) -> pa.Table:
    schema = arrow_schema(manifest)
    options = pacsv.ConvertOptions(
        column_types={field.name: field.type for field in schema},
        null_values=[""],
        strings_can_be_null=True,
    )
    return pacsv.read_csv(path, convert_options=options).select(schema.names)


def _normalize_row(row: dict, column_names: list[str]) -> dict:
    normalized = {}
    for name in column_names:
        value = row.get(name)
        if value is not None and name == "classification_score":
            value = float(value)
        elif value is not None and name == "repo_stars":
            value = int(value)
        elif value is not None and name in {"fork", "archived"}:
            value = bool(value)
        normalized[name] = value
    return normalized


def canonical_hash(table: pa.Table) -> str:
    rows = [_normalize_row(row, table.column_names) for row in table.to_pylist()]
    sort_column = "full_name" if "full_name" in table.column_names else table.column_names[0]
    rows.sort(
        key=lambda row: (
            row[sort_column] or "",
            json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        )
    )
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def query_counts(table: pa.Table, manifest: dict | None = None) -> dict[str, int]:
    if manifest is not None and "workloads" in manifest:
        return {
            operation: apply_workload(table, workload).num_rows
            for operation, workload in load_workloads(manifest).items()
        }
    return {
        "rows": table.num_rows,
        "group_ai_llm": table.filter(pc.equal(table["group"], "AI / LLM")).num_rows,
        "repo_stars_gt_100000": table.filter(
            pc.greater(table["repo_stars"], 100000)
        ).num_rows,
        "full_name_anomalyco_opencode": table.filter(
            pc.equal(table["full_name"], "anomalyco/opencode")
        ).num_rows,
    }


def verify_table(table: pa.Table, manifest: dict) -> dict:
    expected_schema = arrow_schema(manifest)
    if table.schema != expected_schema:
        raise ValueError(f"schema mismatch: expected {expected_schema}, got {table.schema}")
    if table.num_rows != manifest["rows"]:
        raise ValueError(f"row count mismatch: expected {manifest['rows']}, got {table.num_rows}")
    actual_hash = canonical_hash(table)
    if actual_hash != manifest["canonical_hash"]:
        raise ValueError("canonical hash mismatch")
    counts = query_counts(table, manifest)
    if counts != manifest["expected_counts"]:
        raise ValueError(f"query count mismatch: expected {manifest['expected_counts']}, got {counts}")
    return {"canonical_hash": actual_hash, "counts": counts, "passed": True}


def load_dataset(root: Path, dataset_id: str, source: Path | None = None) -> tuple[dict, pa.Table]:
    manifest = load_manifest(root, dataset_id)
    source_path = source or root / ".data" / dataset_id / "source.csv"
    actual_source_sha256 = sha256_bytes(source_path.read_bytes())
    if actual_source_sha256 != manifest["source_sha256"]:
        raise ValueError(
            "source SHA-256 mismatch: "
            f"expected {manifest['source_sha256']}, got {actual_source_sha256}"
        )
    table = read_csv(source_path, manifest)
    verify_table(table, manifest)
    return manifest, table
