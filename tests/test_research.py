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
