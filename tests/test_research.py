import json
from pathlib import Path

import pytest

from format_bench.research import load_research_records


def _write_research_record(tmp_path: Path, value: object) -> None:
    destination = tmp_path / "research" / "formats" / "case.json"
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(value), encoding="utf-8")


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

    fastlanes_attempt = next(
        attempt
        for attempt in records["fastlanes"]["attempts"]
        if "Linux x86_64" in attempt["entrypoint"]
    )
    assert fastlanes_attempt["environment"]["architecture"] == "x86_64"
    assert fastlanes_attempt["result"].startswith("numeric and all five")
    assert fastlanes_attempt["workflow_run"]["run_id"] == "29520329351"
    assert fastlanes_attempt["workflow_run"]["archive_sha256"].startswith("b9270a10")
    assert fastlanes_attempt["workflow_run"]["release_tag"] == "v0.1.0"

    nimble_json = json.dumps(records["nimble"])
    assert "/nix/store/" not in nimble_json
    assert "/opt/homebrew/" not in nimble_json

    manifest = json.loads(
        (
            Path.cwd() / "research" / "probes" / "nimble-dependency-closure.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["status"] == "UNSUPPORTED"
    assert len(manifest["flake_lock_sha256"]) == 64
    assert manifest["source_commits"] == records["nimble"]["source_commits"]
    for name, dependency in manifest["dependencies"].items():
        if name in {"boost", "xsimd"}:
            assert dependency["acquisition"].startswith("Velox commit ")
        else:
            assert dependency["acquisition"].startswith("nixpkgs@")


def test_relative_root_does_not_match_url_punctuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(Path(__file__).parents[1])

    assert set(load_research_records(Path("."))) == {
        "fastlanes",
        "nimble",
        "anyblox",
    }


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([], "research record case.json must be an object"),
        (
            {
                "name": "case",
                "comparability": "PARTIAL",
                "state": "FAILED",
                "source_commits": [],
                "claim_summary": "bounded failure",
            },
            "research source_commits must be an object",
        ),
        (
            {
                "name": "case",
                "comparability": "PARTIAL",
                "state": "FAILED",
                "source_commits": {"core": 7},
                "claim_summary": "bounded failure",
            },
            "research commit is not a full SHA",
        ),
    ],
)
def test_research_records_reject_untyped_boundary_shapes(
    tmp_path: Path, value: object, message: str
) -> None:
    _write_research_record(tmp_path, value)

    with pytest.raises(ValueError, match=message):
        load_research_records(tmp_path)
