from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).parents[1]


def _load_builder() -> ModuleType:
    path = ROOT / "tools" / "build_revalidation_aggregate.py"
    spec = importlib.util.spec_from_file_location("revalidation_aggregate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_revalidation_generator_is_deterministic_and_keeps_provenance(
    tmp_path: Path,
) -> None:
    dataset_id = "github-stars-2026-07-03"
    pair = "csv-tsv"
    _write_json(
        tmp_path / "datasets" / dataset_id / "manifest.json",
        {
            "rows": 4,
            "columns": [{"name": "full_name"}],
            "source_sha256": "source",
            "canonical_hash": "canonical",
            "release_asset": "fixture.csv.zst",
        },
    )
    run = tmp_path / "runs" / "full-20260718-github-parallel-4"
    _write_json(run / "manifest.json", {"environment": {"git_commit": "encode"}})
    _write_json(
        run / "results.json",
        {
            "status": "MEASURED",
            "environment": {"git_commit": "measure"},
            "measurement": {"fresh_processes": 2},
            "equivalence": {"pairs": {pair: {"verdict": "PRACTICALLY_EQUIVALENT"}}},
            "results": {},
        },
    )
    builder = _load_builder()
    builder.ROOT = tmp_path
    builder.OUTPUT = tmp_path / ".data" / "revalidation-20260719"
    builder.DATASETS = (dataset_id,)
    builder.PAIRS = (pair,)
    pilot = builder.OUTPUT / "pilot-contract" / "github" / "attempt-1.json"
    _write_json(pilot, {"state": "COMPLETE"})

    builder.main()
    first = {
        name: (builder.OUTPUT / name).read_bytes()
        for name in ("manifest.json", "results.json", "report.md", "SHA256SUMS.txt")
    }
    stale = builder.OUTPUT / "claims" / "stale.json"
    _write_json(stale, {"stale": True})
    builder.main()

    assert {name: (builder.OUTPUT / name).read_bytes() for name in first} == first
    assert not stale.exists()
    assert pilot.is_file()
    result = json.loads(first["results.json"])
    evidence = result["datasets"][0]["evidence"][0]
    assert result["completion_state"] == "COMPLETE"
    assert evidence["source"]["encoding_commit"] == "encode"
    assert evidence["source"]["measurement_commit"] == "measure"
    assert evidence["source"]["manifest_sha256"] == builder.sha256(
        run / "manifest.json"
    )
    assert result["datasets"][0]["pilot_contract"]["attempts"][0]["sha256"] == (
        builder.sha256(pilot)
    )


def test_revalidation_generator_uses_a_later_complete_candidate(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    incomplete = tmp_path / "incomplete"
    complete = tmp_path / "complete"
    for path, status in ((incomplete, "PARTIAL"), (complete, "MEASURED")):
        _write_json(path / "manifest.json", {})
        _write_json(
            path / "results.json",
            {
                "status": status,
                "equivalence": {
                    "pairs": {"csv-tsv": {"verdict": "PRACTICALLY_EQUIVALENT"}}
                },
            },
        )
    builder.candidates = lambda *_: [incomplete, complete]

    selected, reason = builder.choose_run("dataset", "csv-tsv")

    assert selected == complete
    assert reason is None


def test_revalidation_completion_keeps_inconclusive_measurements_terminal() -> None:
    builder = _load_builder()
    results = {
        "status": "MEASURED",
        "equivalence": {"pairs": {"csv-tsv": {"verdict": "INCONCLUSIVE"}}},
    }

    assert builder.pair_measurement_complete(results, "csv-tsv") is True

    results["equivalence"]["pairs"]["csv-tsv"]["verdict"] = "NOT_APPLICABLE"
    assert builder.pair_measurement_complete(results, "csv-tsv") is False


def test_revalidation_finalizer_is_bounded_and_uses_tracked_tools(
    tmp_path: Path,
) -> None:
    script_path = ROOT / "tools" / "finalize_revalidation.sh"
    script = script_path.read_text()

    assert "sleep " not in script
    assert 'cd "$repo_root"' in script
    assert "tools/build_revalidation_aggregate.py" in script
    assert ".venv/bin/python - <<'PY'" in script
    assert "mkdir -p .data/revalidation-20260719/package-run" in script

    result = subprocess.run(
        [script_path],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "required run is incomplete: runs/" in result.stderr
