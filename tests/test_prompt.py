import csv
import json
from pathlib import Path

import pyarrow as pa
import pytest

from format_bench.canonical import read_csv
from format_bench.prompt import (
    COMPACT_SCHEMA,
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
    expected_compact = (
        "m\tr\tl\ts\tk\tt\td\n"
        "1\tanomalyco/opencode\tTypeScript\t181916\tcoding agent,opencode\t\t"
        "The open source coding agent.\n"
        "1\tautomazeio/vibeproxy\tSwift\t3095\tclaude code,codex,ai coding\t"
        "claude-code,claudecode,cli-proxy,codex,factory-droids,gpt-5-codex\t"
        "Native macOS menu bar app to use your Claude Code & ChatGPT subscriptions "
        "with AI coding tools - no API keys needed\n"
        "1\tbadlogic/pi-skills\tJavaScript\t2110\tcoding agent,claude code,codex\t\t"
        "Skills for pi coding agent (compatible with Claude Code and Codex CLI)\n"
        "1\tBloopAI/vibe-kanban\tRust\t27248\tcoding agent,claude code,codex\t"
        "agent,ai-agents,kanban,management,task-manager\t"
        "Get 10X more out of Claude Code, Codex or any coding agent\n"
    )
    objects = [json.loads(line) for line in paths["object_jsonl"].read_text().splitlines()]
    arrays = [json.loads(line) for line in paths["array_jsonl"].read_text().splitlines()]
    array_schema = json.loads(paths["array_schema"].read_text())
    with paths["compact_tsv"].open(newline="") as handle:
        compact = list(csv.reader(handle, delimiter="\t"))[1:]

    assert objects == expected
    assert tuple(array_schema) == PROMPT_COLUMNS
    assert [dict(zip(PROMPT_COLUMNS, row, strict=True)) for row in arrays] == expected
    assert len(compact) == len(expected) == table.num_rows
    assert paths["compact_tsv"].read_text() == expected_compact


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
    assert metrics["corpus"]["compact_tsv"]["schema_bytes"] > 0
    assert metrics["corpus"]["object_jsonl"]["schema_bytes"] == 0
    assert metrics["retrieval_to_compact_tsv"]["5"]["rows"] == 4


def test_compact_schema_is_exact_and_counted_once(tmp_path: Path) -> None:
    table = fixture_table()
    paths = write_prompt_artifacts(table, tmp_path)
    expected = {
        "m": "taxonomy_id",
        "r": "full_name",
        "l": "language",
        "s": "repo_stars",
        "k": "matched_terms",
        "t": "topics",
        "d": "description",
    }

    assert json.loads(paths["compact_schema"].read_text()) == expected
    assert COMPACT_SCHEMA == expected

    metrics = token_metrics(table, paths)
    compact = metrics["corpus"]["compact_tsv"]
    schema_bytes = paths["compact_schema"].stat().st_size
    payload_bytes = paths["compact_tsv"].stat().st_size
    taxonomy_bytes = paths["taxonomy"].stat().st_size
    assert compact["schema_bytes"] == schema_bytes
    assert compact["payload_bytes"] == payload_bytes
    assert compact["total_bytes"] == taxonomy_bytes + schema_bytes + payload_bytes

    for result in metrics["retrieval_to_compact_tsv"].values():
        assert result["schema_bytes"] == schema_bytes
        expected_total = (
            result["taxonomy_bytes"]
            + result["schema_bytes"]
            + result["payload_bytes"]
        )
        assert expected_total == result["total_bytes"]
        assert result["bytes"] == result["total_bytes"]


def test_compact_schema_and_metrics_are_deterministic_and_other_formats_unchanged(
    tmp_path: Path,
) -> None:
    table = fixture_table()
    first = write_prompt_artifacts(table, tmp_path / "first")
    second = write_prompt_artifacts(table, tmp_path / "second")

    assert first["compact_schema"].read_bytes() == second["compact_schema"].read_bytes()
    first_metrics = token_metrics(table, first)
    second_metrics = token_metrics(table, second)
    assert first_metrics == second_metrics
    assert first_metrics["corpus"]["object_jsonl"]["schema_bytes"] == 0
    assert (
        first_metrics["corpus"]["array_jsonl"]["schema_bytes"]
        == first["array_schema"].stat().st_size
    )
    assert first["compact_tsv"].read_bytes() == second["compact_tsv"].read_bytes()


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


def test_prompt_nonfinite_failure_preserves_existing_artifacts(tmp_path: Path) -> None:
    object_path = tmp_path / "prompt-object.jsonl"
    array_path = tmp_path / "prompt-array.jsonl"
    object_path.write_text("existing-object\n", encoding="utf-8")
    array_path.write_text("existing-array\n", encoding="utf-8")
    table = pa.table(
        {
            "group": ["AI", "AI"],
            "category": ["Tools", "Tools"],
            "micro_category": ["Agents", "Agents"],
            "full_name": ["one/a", "two/b"],
            "language": ["Python", "Rust"],
            "repo_stars": [1.0, float("nan")],
            "matched_terms": ["agent", "agent"],
            "topics": ["ai", "ai"],
            "description": ["one", "two"],
        }
    )

    with pytest.raises(ValueError, match="not JSON compliant"):
        write_prompt_artifacts(table, tmp_path)

    assert object_path.read_text(encoding="utf-8") == "existing-object\n"
    assert array_path.read_text(encoding="utf-8") == "existing-array\n"
