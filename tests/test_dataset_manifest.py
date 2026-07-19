import csv
import json
from pathlib import Path


DATASET = Path("datasets/github-stars-2026-07-03")


def test_stars_manifest_fixes_the_public_contract() -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())

    assert manifest["dataset_id"] == "github-stars-2026-07-03"
    assert manifest["rows"] == 2331
    assert len(manifest["columns"]) == 13
    assert manifest["source_sha256"] == (
        "39cc70109d9dddf947257584e15f2f9a6bc97dcdf0a7bf939c26cccbcda0e22e"
    )
    assert manifest["canonical_hash"] == (
        "2b276e537c8204e6631ece22f6e402322db47d610ce8ac5b30d07d0fe4020e8f"
    )
    assert manifest["expected_counts"] == {
        "rows": 2331,
        "group_ai_llm": 119,
        "repo_stars_gt_100000": 15,
        "full_name_anomalyco_opencode": 1,
    }


def test_fixture_uses_the_manifest_columns() -> None:
    manifest = json.loads((DATASET / "manifest.json").read_text())
    with (DATASET / "fixture.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4
    assert list(rows[0]) == [column["name"] for column in manifest["columns"]]
