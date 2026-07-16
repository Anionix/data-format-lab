from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from format_bench.model import (
    ExecutionState,
    Lane,
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
    TargetTier,
    robustness_verdict,
)
from format_bench.profile_run import _finish, _load
from format_bench.robustness.evidence import ArtifactBudgetExceeded, EvidenceStore
from format_bench.robustness.runner import _process

ARROW_SOURCE_COMMIT = "7932e197eaa00577ff3e83ddf956022df3ef174c"
DEFAULT_NATIVE_BUILD_DIR = Path("native/arrow/build")
_NATIVE_OUTPUT_BUDGET_BYTES = 1024 * 1024


@dataclass(frozen=True)
class NativeTarget:
    name: str
    official_target: str
    tier: TargetTier = TargetTier.EXPERIMENTAL


ARROW_NATIVE_TARGETS: tuple[NativeTarget, ...] = tuple(
    NativeTarget(name, name)
    for name in ("arrow-csv-fuzz", "parquet-arrow-fuzz", "parquet-encoding-fuzz")
)


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _binary(build_dir: Path, target: NativeTarget) -> Path | None:
    candidates = [build_dir / target.name]
    if build_dir.is_dir():
        candidates.extend(sorted(build_dir.rglob(target.name)))
    return next(
        (path for path in candidates if path.is_file() and os.access(path, os.X_OK)),
        None,
    )


def _corpus_source(run_dir: Path, run: dict, target: NativeTarget) -> Path:
    if target.name != "arrow-csv-fuzz":
        for entry in run["formats"]:
            if entry["format"] == "parquet_default" and entry["state"] == ExecutionState.ROUNDTRIP_VERIFIED:
                return run_dir / entry["artifact"]
    return run_dir / run["input"]["source"]


def _base(target: NativeTarget) -> dict[str, object]:
    return {
        "schema_version": "1",
        "contract_version": "1",
        "case_id": f"native-{target.name}",
        "target": target.name,
        "tier": target.tier,
        "expectation": RobustnessExpectation.MUST_NOT_CRASH,
    }


def _case(
    target: NativeTarget,
    run_dir: Path,
    store: EvidenceStore,
    duration_seconds: float,
    fixture: bool,
    run: dict,
    build_dir: Path,
) -> dict[str, object]:
    base = _base(target)
    binary = _binary(build_dir, target)
    if binary is None:
        return {
            **base,
            "observed": ObservedOutcome.UNSUPPORTED,
            "verdict": RobustnessVerdict.INCOMPLETE,
            "details": {"reason": "official target binary not found"},
        }
    source = _corpus_source(run_dir, run, target)
    prefix = Path("native") / target.name
    with tempfile.TemporaryDirectory(dir=run_dir) as temporary:
        artifacts = Path(temporary) / "artifacts"
        artifacts.mkdir()
        command = [
            str(binary),
            "-print_final_stats=1",
            f"-max_total_time={max(1, int(duration_seconds))}",
            f"-timeout={max(1, int(duration_seconds))}",
            f"-artifact_prefix={artifacts.as_posix()}/",
        ]
        if fixture:
            command.append("-runs=1")
        command.append(source.as_posix())
        process, stdout, stderr = _process(
            command, run_dir, duration_seconds + 5, output_budget_bytes=_NATIVE_OUTPUT_BUDGET_BYTES
        )
        if process["timed_out"]:
            observed = ObservedOutcome.TIMED_OUT
        elif process["signal"] is not None:
            observed = ObservedOutcome.CRASHED
        elif process["exit_code"] == 0:
            observed = ObservedOutcome.ACCEPTED
        else:
            observed = ObservedOutcome.HARNESS_FAILED
        result = {
            **base,
            "observed": observed,
            "verdict": robustness_verdict(RobustnessExpectation.MUST_NOT_CRASH, observed),
            "details": {"official_target": target.official_target, "corpus": source.relative_to(run_dir).as_posix()},
            "process": process,
        }
        try:
            records = store.import_path(artifacts, prefix / "artifacts")
            stdout_record = store.store_bytes(prefix / "stdout.txt", stdout.encode())
            stderr_record = store.store_bytes(prefix / "stderr.txt", stderr.encode())
            result.update(
                stdout=f"robustness/{stdout_record.relative_path}",
                stderr=f"robustness/{stderr_record.relative_path}",
                artifact_records=[
                    {"path": f"robustness/{record.relative_path}", "size_bytes": record.size_bytes, "sha256": record.sha256}
                    for record in records
                ],
            )
            store.store_bytes(prefix / "result.json", _json(result))
        except ArtifactBudgetExceeded as error:
            return {
                **base,
                "observed": ObservedOutcome.BUDGET_EXHAUSTED,
                "verdict": RobustnessVerdict.INCOMPLETE,
                "details": {"error_type": type(error).__name__, "message": str(error)},
            }
        return result


def run_native(
    root: Path,
    run_dir: Path,
    *,
    duration_seconds: float = 900.0,
    artifact_budget_mib: int = 1024,
    targets: tuple[NativeTarget, ...] | None = None,
    build_dir: Path | None = None,
) -> Path:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if artifact_budget_mib <= 0:
        raise ValueError("artifact_budget_mib must be positive")
    run, _ = _load(run_dir)
    effective_build_dir = build_dir or root / DEFAULT_NATIVE_BUILD_DIR
    store = EvidenceStore(run_dir / "robustness", artifact_budget_mib * 1024 * 1024)
    selected = targets or ARROW_NATIVE_TARGETS
    observations = [
        _case(target, run_dir, store, duration_seconds, bool(run["fixture"]), run, effective_build_dir)
        for target in selected
    ]
    summary = {verdict.value: 0 for verdict in RobustnessVerdict}
    for item in observations:
        summary[str(item["verdict"])] += 1
    evidence = {
        "robustness_v1": {
            "contract_version": "1",
            "state": ExecutionState.BENCHMARKED,
            "suite": "native",
            "config": {
                "seed": run["seed"],
                "generated_cases": 0,
                "mutations_per_target": 0,
                "case_timeout_seconds": duration_seconds + 5,
                "artifact_budget_mib": artifact_budget_mib,
                "duration_seconds": duration_seconds,
                "source_commit": ARROW_SOURCE_COMMIT,
                "build_dir": effective_build_dir.relative_to(root).as_posix()
                if effective_build_dir.is_relative_to(root)
                else DEFAULT_NATIVE_BUILD_DIR.as_posix(),
            },
            "cases": observations,
            "summary": summary,
        }
    }
    return _finish(root, run_dir, run, Lane.ROBUSTNESS, evidence)
