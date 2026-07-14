import json
from pathlib import Path

from format_bench.formats.text import CsvAdapter, ObjectJsonlAdapter
from format_bench.workflow import prepare_run, verify_run


DATASET = "github-stars-2026-07-03"


def test_prepare_and_verify_fixture_record_relative_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    chosen = (CsvAdapter(), ObjectJsonlAdapter())
    prepared = prepare_run(root, DATASET, run_dir, fixture=True, selected=chosen)

    manifest = json.loads((prepared / "manifest.json").read_text())
    assert manifest["state"] == "ENCODED"
    assert manifest["fixture"] is True
    assert manifest["rankable"] is False
    assert all(not Path(entry["artifact"]).is_absolute() for entry in manifest["formats"])
    assert {entry["state"] for entry in manifest["formats"]} == {"ENCODED"}

    verify_run(prepared, {adapter.describe().name: adapter for adapter in chosen})
    verified = json.loads((prepared / "manifest.json").read_text())
    assert verified["state"] == "ROUNDTRIP_VERIFIED"
    assert {entry["state"] for entry in verified["formats"]} == {
        "ROUNDTRIP_VERIFIED"
    }
    assert all(entry["verification"]["passed"] for entry in verified["formats"])
