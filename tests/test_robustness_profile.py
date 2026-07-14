import json
from pathlib import Path

from format_bench.formats.text import CsvAdapter
from format_bench.robustness.profile import run_bounded
from format_bench.robustness.targets import core_targets
from format_bench.workflow import prepare_run, verify_run


DATASET = "github-stars-2026-07-03"


def test_bounded_fixture_writes_versioned_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    adapter = CsvAdapter()
    prepare_run(root, DATASET, run_dir, fixture=True, selected=(adapter,))
    verify_run(run_dir, {"csv": adapter})

    result_path = run_bounded(
        root,
        run_dir,
        generated_count=0,
        targets=(core_targets()[0],),
    )
    results = json.loads(result_path.read_text())
    evidence = results["results"]["robustness_v1"]
    assert results["schema_version"] == evidence["contract_version"] == "1"
    assert evidence["state"] == "BENCHMARKED"
    assert evidence["summary"] == {
        "FAIL": 0,
        "INCOMPLETE": 0,
        "NOT_APPLICABLE": 0,
        "PASS": 3,
    }
    assert all(
        {
            "schema_version",
            "contract_version",
            "expectation",
            "observed",
            "verdict",
        }
        <= item.keys()
        for item in evidence["cases"]
    )
    valid = next(item for item in evidence["cases"] if item["case_id"] == "rows-1")
    assert len(valid["input_canonical_hash"]) == 64
    assert len(valid["input_arrow"]["sha256"]) == 64
    assert all(len(record["sha256"]) == 64 for record in valid["artifact_records"])
