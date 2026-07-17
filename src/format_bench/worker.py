from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .canonical import read_csv
from .fair import FairOperation, apply_arrow, expected_rows, result_evidence
from .registry import adapter_map
from .runner import measure_callable


def _relative(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("run manifest paths must be relative")
    return run_dir / path


def run_fair_worker(run_dir: Path, format_name: str, operation: FairOperation) -> dict:
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    dataset_manifest = json.loads(
        _relative(run_dir, run_manifest["input"]["manifest"]).read_text(encoding="utf-8")
    )
    entry = next(item for item in run_manifest["formats"] if item["format"] == format_name)
    adapter = adapter_map()[format_name]
    artifact = _relative(run_dir, entry["artifact"])

    def invoke() -> int:
        return adapter.scan(artifact, dataset_manifest, operation).num_rows

    measured = measure_callable(
        invoke,
        expected_rows(operation, dataset_manifest),
        int(os.environ.get("FORMAT_BENCH_WARMUPS", "5")),
        int(os.environ.get("FORMAT_BENCH_ITERATIONS", "30")),
    )
    source = read_csv(_relative(run_dir, run_manifest["input"]["source"]), dataset_manifest)
    expected = result_evidence(apply_arrow(source, operation, dataset_manifest))
    actual = result_evidence(adapter.scan(artifact, dataset_manifest, operation))
    if actual != expected:
        raise ValueError(f"normalized operation result mismatch: {actual} != {expected}")
    return {**measured, "evidence": actual}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--format", required=True)
    parser.add_argument("--operation", type=FairOperation, required=True)
    args = parser.parse_args()
    print(json.dumps(run_fair_worker(args.run_dir, args.format, args.operation)))


if __name__ == "__main__":
    main()
