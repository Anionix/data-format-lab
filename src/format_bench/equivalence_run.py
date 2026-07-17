from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from .equivalence import EquivalenceBounds, EquivalenceVerdict
from .equivalence_compare import PAIR_SPECS, pair_evidence
from .fair import OPERATIONS, expected_rows
from .model import Comparability, ExecutionState, transition
from .runner import Job, MeasurementConfig, new_results, run_jobs


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_equivalence(
    root: Path,
    run_dir: Path,
    *,
    pairs: tuple[str, ...] | None = None,
    config: MeasurementConfig | None = None,
) -> Path:
    manifest_path = run_dir / "manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if run_manifest["state"] != ExecutionState.ROUNDTRIP_VERIFIED:
        raise ValueError("equivalence run requires a round-trip verified run directory")
    input_manifest = json.loads(
        (run_dir / run_manifest["input"]["manifest"]).read_text(encoding="utf-8")
    )
    selected_pairs = pairs or tuple(PAIR_SPECS)
    unknown = sorted(set(selected_pairs) - PAIR_SPECS.keys())
    if unknown:
        raise ValueError(f"unknown equivalence pair: {', '.join(unknown)}")
    entries = {
        entry["format"]: entry
        for entry in run_manifest["formats"]
        if entry["state"] == ExecutionState.ROUNDTRIP_VERIFIED
        and entry["comparability"] == Comparability.FULL_COMPARABLE
    }
    missing_by_pair: dict[str, str] = {}
    measured_names: set[str] = set()
    for pair in selected_pairs:
        spec = PAIR_SPECS[pair]
        required = (spec["reference"], *spec["candidates"])
        missing = [name for name in required if name not in entries]
        wrong_lane = [
            name
            for name in required
            if name in entries and entries[name]["lane"] not in spec["allowed_lanes"]
        ]
        if missing:
            missing_by_pair[pair] = f"round-trip verified FULL_COMPARABLE formats missing: {', '.join(missing)}"
        elif wrong_lane:
            missing_by_pair[pair] = f"formats are outside the pair lane contract: {', '.join(wrong_lane)}"
        else:
            measured_names.update(required)
    measurement = config or (
        MeasurementConfig(fresh_processes=2, warmups=1, iterations=2)
        if run_manifest.get("fixture")
        else MeasurementConfig()
    )
    jobs = [
        Job(
            f"{name}/{operation.value}",
            (
                sys.executable,
                "-m",
                "format_bench.worker",
                "--run-dir",
                str(run_dir.resolve()),
                "--format",
                name,
                "--operation",
                operation.value,
            ),
            expected_rows(operation, input_manifest),
        )
        for name in sorted(measured_names)
        for operation in OPERATIONS
    ]
    measured = run_jobs(jobs, measurement, root)
    failed = [job_id for job_id, result in measured.items() if result["status"] != "MEASURED"]
    bounds = EquivalenceBounds()
    pairs_evidence = {}
    for pair in selected_pairs:
        if pair in missing_by_pair:
            pairs_evidence[pair] = {
                "lane": PAIR_SPECS[pair]["lane"],
                "verdict": EquivalenceVerdict.NOT_APPLICABLE,
                "failure_reason": missing_by_pair[pair],
            }
            continue
        if failed:
            pairs_evidence[pair] = {
                "lane": PAIR_SPECS[pair]["lane"],
                "verdict": EquivalenceVerdict.NOT_APPLICABLE,
                "failure_reason": f"benchmark jobs failed: {', '.join(failed)}",
            }
            continue
        pairs_evidence[pair] = pair_evidence(
            PAIR_SPECS[pair], measured, entries, bounds, measurement.seed
        )
    result_state = ExecutionState.FAILED if failed else ExecutionState.BENCHMARKED
    run_manifest["state"] = transition(
        ExecutionState.ROUNDTRIP_VERIFIED, result_state
    )
    run_manifest["equivalence"] = {
        "contract_version": "1",
        "bounds": asdict(bounds),
        "pairs": pairs_evidence,
    }
    _write_json(manifest_path, run_manifest)
    results = new_results(root, run_dir.name, measurement)
    results["profile"] = "equivalence"
    results["dataset_id"] = run_manifest["dataset_id"]
    results["state"] = result_state
    results["equivalence"] = run_manifest["equivalence"]
    results["results"] = measured
    results["status"] = "FAILED" if failed else "MEASURED"
    _write_json(run_dir / "results.json", results)
    return run_dir / "results.json"
