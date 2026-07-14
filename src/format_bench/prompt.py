from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import tiktoken


PROMPT_COLUMNS = (
    "taxonomy_id",
    "full_name",
    "language",
    "repo_stars",
    "matched_terms",
    "topics",
    "description",
)
TOKENIZERS = ("o200k_base", "cl100k_base")
NULL_MARKER = r"\N"


def _terms(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _taxonomy_sort_key(key: tuple[str | None, ...]) -> tuple[tuple[bool, str], ...]:
    return tuple((value is not None, value or "") for value in key)


def _taxonomy_rows(taxonomy: list[tuple]) -> list[tuple]:
    return [
        tuple(NULL_MARKER if value is None else value for value in row)
        for row in taxonomy
    ]


def prompt_records(table: pa.Table) -> tuple[list[dict[str, Any]], list[tuple]]:
    rows = table.to_pylist()
    keys = sorted(
        {(row["group"], row["category"], row["micro_category"]) for row in rows},
        key=_taxonomy_sort_key,
    )
    taxonomy = {key: index + 1 for index, key in enumerate(keys)}
    records = []
    for row in rows:
        key = (row["group"], row["category"], row["micro_category"])
        records.append(
            {
                "taxonomy_id": taxonomy[key],
                "full_name": row["full_name"],
                "language": row["language"],
                "repo_stars": row["repo_stars"],
                "matched_terms": _terms(row["matched_terms"]),
                "topics": _terms(row["topics"]),
                "description": row["description"],
            }
        )
    return records, [(taxonomy[key], *key) for key in keys]


def write_prompt_artifacts(table: pa.Table, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    records, taxonomy = prompt_records(table)
    paths = {
        "taxonomy": directory / "prompt-taxonomy.tsv",
        "compact_tsv": directory / "prompt-compact.tsv",
        "object_jsonl": directory / "prompt-object.jsonl",
        "array_jsonl": directory / "prompt-array.jsonl",
        "array_schema": directory / "prompt-array-schema.json",
    }
    with paths["taxonomy"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["m", "g", "c", "mc"])
        writer.writerows(_taxonomy_rows(taxonomy))
    with paths["compact_tsv"].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["m", "r", "l", "s", "k", "t", "d"])
        for row in records:
            writer.writerow(
                [
                    row["taxonomy_id"],
                    row["full_name"],
                    row["language"] or "",
                    row["repo_stars"],
                    ",".join(row["matched_terms"]),
                    ",".join(row["topics"]),
                    row["description"] or "",
                ]
            )
    with paths["object_jsonl"].open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    with paths["array_jsonl"].open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(
                json.dumps([row[name] for name in PROMPT_COLUMNS], ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
    paths["array_schema"].write_text(
        json.dumps(PROMPT_COLUMNS, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return paths


def _token_counts(text: str) -> dict[str, int]:
    return {
        name: len(tiktoken.get_encoding(name).encode(text, disallowed_special=()))
        for name in TOKENIZERS
    }


def _retrieval_tsv(records: list[dict], taxonomy: list[tuple]) -> str:
    used = {row["taxonomy_id"] for row in records}
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(["m", "g", "c", "mc"])
    writer.writerows(
        _taxonomy_rows([row for row in taxonomy if row[0] in used])
    )
    writer.writerow(["m", "r", "l", "s", "k", "t", "d"])
    for row in records:
        writer.writerow(
            [
                row["taxonomy_id"],
                row["full_name"],
                row["language"] or "",
                row["repo_stars"],
                ",".join(row["matched_terms"]),
                ",".join(row["topics"]),
                row["description"] or "",
            ]
        )
    return output.getvalue()


def token_metrics(table: pa.Table, paths: dict[str, Path]) -> dict:
    taxonomy_text = paths["taxonomy"].read_text(encoding="utf-8")
    corpus = {}
    for name in ("compact_tsv", "object_jsonl", "array_jsonl"):
        payload = paths[name].read_text(encoding="utf-8")
        schema = (
            paths["array_schema"].read_text(encoding="utf-8")
            if name == "array_jsonl"
            else ""
        )
        text = taxonomy_text + schema + payload
        corpus[name] = {
            "payload_bytes": paths[name].stat().st_size,
            "taxonomy_bytes": paths["taxonomy"].stat().st_size,
            "schema_bytes": len(schema.encode("utf-8")),
            "total_bytes": len(text.encode("utf-8")),
            "tokens": _token_counts(text),
        }
    records, taxonomy = prompt_records(table)
    records.sort(key=lambda row: (-row["repo_stars"], row["full_name"]))
    retrieval = {}
    for count in (5, 10, 20):
        text = _retrieval_tsv(records[:count], taxonomy)
        retrieval[str(count)] = {
            "rows": min(count, len(records)),
            "bytes": len(text.encode("utf-8")),
            "tokens": _token_counts(text),
        }
    return {
        "contract": "prompt_v1; taxonomy and required schemas included once",
        "binary_direct_tokens": None,
        "corpus": corpus,
        "retrieval_to_compact_tsv": retrieval,
    }
