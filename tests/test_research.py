from pathlib import Path

from format_bench.research import load_research_records


def test_negative_research_records_are_pinned_and_unranked() -> None:
    records = load_research_records(Path.cwd())

    assert set(records) == {"fastlanes", "nimble", "anyblox"}
    assert records["fastlanes"]["comparability"] == "PARTIAL"
    assert records["nimble"]["comparability"] == "UNAVAILABLE"
    assert records["anyblox"]["state"] == "FAILED"
    assert all(record["attempts"] for record in records.values())
    assert all(record["retry_when"] for record in records.values())
