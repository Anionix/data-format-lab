from __future__ import annotations

import json
import sys
from pathlib import Path

from .fair import OPERATIONS, expected_rows
from .model import ExecutionState, transition
from .runner import Job, MeasurementConfig, new_results, run_jobs


def run_fair(root: Path, run_dir: Path, config: MeasurementConfig | None = None) -> Path:
    manifest_path = run_dir / "manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if run_manifest["state"] != ExecutionState.ROUNDTRIP_VERIFIED:
        raise ValueError("fair run requires a round-trip verified run directory")
    dataset_manifest = json.loads(
        (run_dir / run_manifest["input"]["manifest"]).read_text(encoding="utf-8")
    )
    measurement = config or (
        MeasurementConfig(fresh_processes=1, warmups=0, iterations=1)
        if run_manifest["fixture"]
        else MeasurementConfig()
    )
    entries = {
        entry["format"]: entry
        for entry in run_manifest["formats"]
        if entry["state"] == ExecutionState.ROUNDTRIP_VERIFIED
    }
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
            expected_rows(operation, dataset_manifest),
        )
        for name in entries
        for operation in OPERATIONS
    ]
    measured = run_jobs(jobs, measurement, root)

    results = new_results(root, run_dir.name, measurement)
    results.update(
        {
            "profile": "fair",
            "dataset_id": run_manifest["dataset_id"],
            "state": ExecutionState.BENCHMARKED,
            "results": measured,
        }
    )
    results_path = run_dir / "results.json"
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")

    for name, entry in entries.items():
        failures = [
            result["reason"]
            for job_id, result in measured.items()
            if job_id.startswith(f"{name}/") and result["status"] == "FAILED"
        ]
        if failures:
            entry["state"] = ExecutionState.FAILED
            entry["failure_reason"] = "; ".join(failures)
        else:
            entry["state"] = transition(
                ExecutionState.ROUNDTRIP_VERIFIED, ExecutionState.BENCHMARKED
            )
    run_manifest["state"] = ExecutionState.BENCHMARKED
    run_manifest["profile"] = "fair"
    manifest_path.write_text(json.dumps(run_manifest, indent=2, sort_keys=True) + "\n")
    return results_path
