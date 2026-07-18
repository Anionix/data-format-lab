from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pyarrow as pa

from .canonical import read_csv
from .fair import Operation, apply_arrow, expected_rows, result_evidence
from .registry import adapter_map
from .runner import measure_callable


def _relative(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("run manifest paths must be relative")
    if run_dir.is_symlink():
        raise ValueError("run directory must not be a symlink")
    candidate = run_dir / path
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError("run manifest paths must not resolve through symlinks")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(run_dir.resolve())
    except ValueError as error:
        raise ValueError("run manifest path escapes run directory") from error
    return candidate


def run_fair_worker(run_dir: Path, format_name: str, operation: Operation) -> dict:
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    dataset_manifest = json.loads(
        _relative(run_dir, run_manifest["input"]["manifest"]).read_text(encoding="utf-8")
    )
    entry = next(item for item in run_manifest["formats"] if item["format"] == format_name)
    adapter = adapter_map()[format_name]
    artifact = _relative(run_dir, entry["artifact"])
    source = read_csv(_relative(run_dir, run_manifest["input"]["source"]), dataset_manifest)
    expected = result_evidence(apply_arrow(source, operation, dataset_manifest))
    full_evidence_checked = False

    def invoke() -> pa.Table:
        return adapter.scan(artifact, dataset_manifest, operation)

    def validate(actual: pa.Table) -> None:
        nonlocal full_evidence_checked
        if not full_evidence_checked:
            actual_evidence = result_evidence(actual)
            if actual_evidence != expected:
                raise ValueError(
                    f"normalized operation result mismatch: {actual_evidence} != {expected}"
                )
            full_evidence_checked = True
            return
        actual_schema = [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in actual.schema
        ]
        if {
            "rows": actual.num_rows,
            "columns": actual.column_names,
            "schema": actual_schema,
        } != {key: expected[key] for key in ("rows", "columns", "schema")}:
            raise ValueError("normalized operation result shape changed")

    measured = measure_callable(
        invoke,
        expected_rows(operation, dataset_manifest),
        int(os.environ.get("FORMAT_BENCH_WARMUPS", "5")),
        int(os.environ.get("FORMAT_BENCH_ITERATIONS", "30")),
        result_count=lambda table: table.num_rows,
        validate=validate,
    )
    return {**measured, "evidence": expected}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--format", required=True)
    parser.add_argument("--operation", required=True)
    args = parser.parse_args()
    print(json.dumps(run_fair_worker(args.run_dir, args.format, args.operation)))


if __name__ == "__main__":
    main()
