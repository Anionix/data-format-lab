from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from .equivalence import EquivalenceBounds, EquivalenceVerdict
from .equivalence_compare import (
    EQUIVALENCE_CONTRACT_VERSION,
    PAIR_SPECS,
    pair_contract,
    pair_evidence,
)
from .fair import expected_rows, operations_for
from .model import Comparability, ExecutionState, transition
from .runner import (
    Job,
    MeasurementConfig,
    measurement_metadata,
    new_results,
    parallel_worker_counts,
    run_jobs,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_equivalence(
    root: Path,
    run_dir: Path,
    *,
    pairs: tuple[str, ...] | None = None,
    config: MeasurementConfig | None = None,
    parallel: bool = False,
) -> Path:
    manifest_path = run_dir / "manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if run_manifest["state"] != ExecutionState.ROUNDTRIP_VERIFIED:
        raise ValueError("equivalence run requires a round-trip verified run directory")
    input_manifest = json.loads(
        (run_dir / run_manifest["input"]["manifest"]).read_text(encoding="utf-8")
    )
    operations = operations_for(input_manifest)
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
            f"{name}/{operation}",
            (
                sys.executable,
                "-m",
                "format_bench.worker",
                "--run-dir",
                str(run_dir.resolve()),
                "--format",
                name,
                "--operation",
                operation,
            ),
            expected_rows(operation, input_manifest),
        )
        for name in sorted(measured_names)
        for operation in operations
    ]
    worker_counts = parallel_worker_counts(len(jobs), parallel=parallel)
    bounds = EquivalenceBounds()
    equivalence_contract = {
        "contract_version": EQUIVALENCE_CONTRACT_VERSION,
        "bounds": asdict(bounds),
        "parallel_jobs": parallel,
        **worker_counts,
        "primary_endpoints": {
            pair: dict(PAIR_SPECS[pair]["primary_endpoint"])
            for pair in selected_pairs
        },
    }
    # LLM contract: ROUNDTRIP_VERIFIED -> PRIMARY_ENDPOINT_PREREGISTERED ->
    # BENCHMARKED; endpoint identity is durable before the first measurement.
    run_manifest["equivalence"] = equivalence_contract
    _write_json(manifest_path, run_manifest)
    measured = run_jobs(jobs, measurement, root, parallel=parallel)
    failed = {
        job_id for job_id, result in measured.items() if result["status"] != "MEASURED"
    }
    pairs_evidence = {}
    for pair in selected_pairs:
        if pair in missing_by_pair:
            pairs_evidence[pair] = {
                "lane": PAIR_SPECS[pair]["lane"],
                **pair_contract(PAIR_SPECS[pair]),
                "verdict": EquivalenceVerdict.NOT_APPLICABLE,
                "failure_reason": missing_by_pair[pair],
            }
            continue
        required_names = {
            PAIR_SPECS[pair]["reference"],
            *PAIR_SPECS[pair]["candidates"],
        }
        pair_failed = sorted(
            job_id
            for job_id in failed
            if job_id.split("/", 1)[0] in required_names
        )
        if pair_failed:
            pairs_evidence[pair] = {
                "lane": PAIR_SPECS[pair]["lane"],
                **pair_contract(PAIR_SPECS[pair]),
                "verdict": EquivalenceVerdict.NOT_APPLICABLE,
                "failure_reason": f"benchmark jobs failed: {', '.join(pair_failed)}",
            }
            continue
        pairs_evidence[pair] = pair_evidence(
            PAIR_SPECS[pair], measured, entries, bounds, measurement.seed, operations
        )
    successful_names = set(measured_names)
    for job_id in failed:
        successful_names.discard(job_id.split("/", 1)[0])
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    for name in measured_names:
        entry = entries[name]
        name_failed = sorted(
            job_id for job_id in failed if job_id.split("/", 1)[0] == name
        )
        if name_failed:
            entry["state"] = ExecutionState.FAILED
            entry["failure_reason"] = f"benchmark jobs failed: {', '.join(name_failed)}"
        else:
            entry["state"] = transition(
                ExecutionState.ROUNDTRIP_VERIFIED, ExecutionState.BENCHMARKED
            )
    # A missing pair is still reportable terminal evidence; only an execution
    # failure without any other evidence makes the run itself non-reportable.
    result_state = (
        ExecutionState.BENCHMARKED
        if successful_names or missing_by_pair
        else ExecutionState.FAILED
    )
    run_manifest["state"] = transition(
        ExecutionState.ROUNDTRIP_VERIFIED, result_state
    )
    run_manifest["equivalence"] = {
        **equivalence_contract,
        "pairs": pairs_evidence,
    }
    run_manifest["measurement"] = measurement_metadata(measurement)
    _write_json(manifest_path, run_manifest)
    results = new_results(root, run_dir.name, measurement)
    results["profile"] = "equivalence"
    results["dataset_id"] = run_manifest["dataset_id"]
    results["state"] = result_state
    results["equivalence"] = run_manifest["equivalence"]
    results["parallel_jobs"] = parallel
    results["results"] = measured
    results["status"] = (
        "MEASURED"
        if not failed and successful_names
        else "PARTIAL"
        if failed and (successful_names or missing_by_pair)
        else "UNSUPPORTED"
        if missing_by_pair
        else "FAILED"
    )
    _write_json(run_dir / "results.json", results)
    return run_dir / "results.json"
