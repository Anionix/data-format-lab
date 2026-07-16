import json
from pathlib import Path

import pytest

from format_bench.research import load_research_records


def test_negative_research_records_are_pinned_and_unranked() -> None:
    records = load_research_records(Path.cwd())

    assert set(records) == {"fastlanes", "nimble", "anyblox"}
    assert records["fastlanes"]["comparability"] == "PARTIAL"
    assert records["nimble"]["comparability"] == "UNAVAILABLE"
    assert records["anyblox"]["state"] == "FAILED"
    assert all(record["attempts"] for record in records.values())
    assert all(record["claim_summary"] for record in records.values())
    assert all(record["retry_when"] for record in records.values())
    assert "checksum-complete dataset" in records["anyblox"]["retry_when"]
    assert ".anyblox bundle" in records["anyblox"]["retry_when"]

    fastlanes_attempt = records["fastlanes"]["attempts"][-1]
    assert fastlanes_attempt["environment"]["architecture"] == "x86_64"
    assert fastlanes_attempt["result"]["mixed"].startswith("HARNESS_FAILED")
    assert fastlanes_attempt["workflow_run"]["run_id"] == "29520329351"

    nimble_json = json.dumps(records["nimble"])
    assert "/nix/store/" not in nimble_json
    assert "/opt/homebrew/" not in nimble_json


def test_relative_root_does_not_match_url_punctuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(Path(__file__).parents[1])

    assert set(load_research_records(Path("."))) == {
        "fastlanes",
        "nimble",
        "anyblox",
    }
