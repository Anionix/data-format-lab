import csv
import json
from pathlib import Path

import pyarrow as pa

from format_bench.canonical import read_csv
from format_bench.prompt import (
    NULL_MARKER,
    PROMPT_COLUMNS,
    prompt_records,
    token_metrics,
    write_prompt_artifacts,
)


DATASET = Path("datasets/github-stars-2026-07-03")


def fixture_table():
    manifest = json.loads((DATASET / "manifest.json").read_text())
    return read_csv(DATASET / "fixture.csv", manifest)


def test_prompt_artifacts_represent_the_same_records(tmp_path: Path) -> None:
    table = fixture_table()
    expected, _ = prompt_records(table)
    paths = write_prompt_artifacts(table, tmp_path)
    objects = [json.loads(line) for line in paths["object_jsonl"].read_text().splitlines()]
    arrays = [json.loads(line) for line in paths["array_jsonl"].read_text().splitlines()]
    array_schema = json.loads(paths["array_schema"].read_text())
    with paths["compact_tsv"].open(newline="") as handle:
        compact = list(csv.reader(handle, delimiter="\t"))[1:]

    assert objects == expected
    assert tuple(array_schema) == PROMPT_COLUMNS
    assert [dict(zip(PROMPT_COLUMNS, row, strict=True)) for row in arrays] == expected
    assert len(compact) == len(expected) == table.num_rows


def test_token_metrics_include_taxonomy_and_exact_encoders(tmp_path: Path) -> None:
    table = fixture_table()
    paths = write_prompt_artifacts(table, tmp_path)
    metrics = token_metrics(table, paths)

    assert metrics["binary_direct_tokens"] is None
    for result in metrics["corpus"].values():
        assert result["taxonomy_bytes"] == paths["taxonomy"].stat().st_size
        assert set(result["tokens"]) == {"o200k_base", "cl100k_base"}
        assert all(value > 0 for value in result["tokens"].values())
    assert metrics["corpus"]["array_jsonl"]["schema_bytes"] > 0
    assert metrics["corpus"]["compact_tsv"]["schema_bytes"] == 0
    assert metrics["corpus"]["object_jsonl"]["schema_bytes"] == 0
    assert metrics["retrieval_to_compact_tsv"]["5"]["rows"] == 4


def test_nullable_taxonomy_is_distinct_and_deterministic(tmp_path: Path) -> None:
    table = pa.table(
        {
            "group": ["AI", None, "AI"],
            "category": [None, "Tools", ""],
            "micro_category": ["Agents", None, "Agents"],
            "full_name": ["one/a", "two/b", "three/c"],
            "language": [None, "Python", "Rust"],
            "repo_stars": [1, 2, 3],
            "matched_terms": [None, "tool", "agent"],
            "topics": ["ai", None, "ai,agent"],
            "description": [None, "two", "three"],
        }
    )

    records, taxonomy = prompt_records(table)
    paths = write_prompt_artifacts(table, tmp_path)

    assert [record["taxonomy_id"] for record in records] == [2, 1, 3]
    assert taxonomy == [
        (1, None, "Tools", None),
        (2, "AI", None, "Agents"),
        (3, "AI", "", "Agents"),
    ]
    assert NULL_MARKER in paths["taxonomy"].read_text()
