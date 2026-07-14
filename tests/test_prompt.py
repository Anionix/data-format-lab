import csv
import json
from pathlib import Path

from format_bench.canonical import read_csv
from format_bench.prompt import PROMPT_COLUMNS, prompt_records, token_metrics, write_prompt_artifacts


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
    with paths["compact_tsv"].open(newline="") as handle:
        compact = list(csv.reader(handle, delimiter="\t"))[1:]

    assert objects == expected
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
    assert metrics["retrieval_to_compact_tsv"]["5"]["rows"] == 4
