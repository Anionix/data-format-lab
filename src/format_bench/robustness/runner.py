from __future__ import annotations

import json
import hashlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO, NotRequired, Sequence, TypedDict, cast

from format_bench.model import (
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
    robustness_verdict,
)
from format_bench.robustness.paths import reject_symlink_tree

MAX_WORKER_DETAILS_BYTES = 4096


class ProcessEvidence(TypedDict):
    exit_code: int | None
    signal: int | None
    timed_out: bool
    duration_ms: float
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    output_budget_bytes: int | None
    output_exhausted: bool


class RequestPayload(TypedDict):
    schema_version: str
    contract_version: str
    case_id: str
    target: str
    expectation: str
    manifest: str
    artifact: str


class WorkerResponse(TypedDict):
    observed: str
    details: dict[str, object]


class CaseResult(TypedDict):
    case_id: str
    target: str
    expectation: RobustnessExpectation
    observed: ObservedOutcome
    verdict: RobustnessVerdict
    details: dict[str, object]
    process: ProcessEvidence
    stdout: str
    stderr: str
    schema_version: NotRequired[str]
    contract_version: NotRequired[str]
    tier: NotRequired[object]
    input_canonical_hash: NotRequired[str]
    input_arrow: NotRequired[object]
    artifact_records: NotRequired[object]
    mutation: NotRequired[object]


def _json_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise TypeError(f"{label} keys must be strings")
    return cast(dict[str, object], mapping)


def _string_field(value: dict[str, object], name: str) -> str:
    field = value.get(name)
    if not isinstance(field, str):
        raise TypeError(f"{name} must be a string")
    return field


def _request_payload(path: Path) -> RequestPayload:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    payload = _json_object(value, "request")
    return {
        "schema_version": _string_field(payload, "schema_version"),
        "contract_version": _string_field(payload, "contract_version"),
        "case_id": _string_field(payload, "case_id"),
        "target": _string_field(payload, "target"),
        "expectation": _string_field(payload, "expectation"),
        "manifest": _string_field(payload, "manifest"),
        "artifact": _string_field(payload, "artifact"),
    }


def _worker_response(stdout: str) -> WorkerResponse:
    value: object = json.loads(stdout.strip())
    response = _json_object(value, "worker response")
    details: object = response.get("details", {})
    return {
        "observed": _string_field(response, "observed"),
        "details": _bounded_details(_json_object(details, "worker response details")),
    }


def _bounded_details(details: dict[str, object]) -> dict[str, object]:
    encoded = (json.dumps({"details": details}, indent=2, sort_keys=True) + "\n").encode()
    if len(encoded) <= MAX_WORKER_DETAILS_BYTES:
        return details
    return {
        "truncated": True,
        "original_size_bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _relative(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("robustness paths must be safe relative paths")
    target = root / path
    if any(item.is_symlink() for item in (target, *target.parents) if item != root.parent):
        raise ValueError("robustness path contains a symlink")
    if not target.resolve(strict=False).is_relative_to(root.resolve()):
        raise ValueError("robustness path escapes run directory")
    if target.exists():
        reject_symlink_tree(target, "robustness path tree contains a symlink")
    return target


def _save(root: Path, value: str | Path, content: str) -> str:
    path = _relative(root, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _relative(root, value)
    with path.open("x", encoding="utf-8", errors="replace") as handle:
        handle.write(content)
    return path.relative_to(root).as_posix()


def _tail(handle: BinaryIO, size: int, limit: int) -> str:
    handle.seek(max(0, size - limit))
    return handle.read(limit).decode("utf-8", errors="ignore")


def _process(
    command: Sequence[str],
    cwd: Path,
    timeout: float,
    output_budget_bytes: int | None = None,
) -> tuple[ProcessEvidence, str, str]:
    if output_budget_bytes is not None and output_budget_bytes < 0:
        raise ValueError("output budget must be non-negative")
    started = time.perf_counter_ns()
    env = os.environ.copy()
    source_root = str(Path(__file__).parents[2])
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (source_root, env.get("PYTHONPATH")) if item
    )
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            list(command), cwd=cwd, stdout=stdout_file, stderr=stderr_file,
            start_new_session=True, env=env,
        )
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        stdout_bytes = os.fstat(stdout_file.fileno()).st_size
        stderr_bytes = os.fstat(stderr_file.fileno()).st_size
        budget = stdout_bytes + stderr_bytes if output_budget_bytes is None else output_budget_bytes
        stdout_limit = min(stdout_bytes, budget // 2)
        stderr_limit = min(stderr_bytes, budget - stdout_limit)
        remaining = budget - stdout_limit - stderr_limit
        stdout_limit += min(stdout_bytes - stdout_limit, remaining)
        remaining = budget - stdout_limit - stderr_limit
        stderr_limit += min(stderr_bytes - stderr_limit, remaining)
        stdout = _tail(stdout_file, stdout_bytes, stdout_limit)
        stderr = _tail(stderr_file, stderr_bytes, stderr_limit)
    duration_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    return {
        "exit_code": process.returncode if not timed_out else None,
        "signal": -process.returncode if process.returncode is not None and process.returncode < 0 else None,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "stdout_truncated": stdout_limit < stdout_bytes,
        "stderr_truncated": stderr_limit < stderr_bytes,
        "output_budget_bytes": output_budget_bytes,
        "output_exhausted": stdout_limit + stderr_limit < stdout_bytes + stderr_bytes,
    }, stdout, stderr


def _outcome(
    process: ProcessEvidence, stdout: str
) -> tuple[ObservedOutcome, dict[str, object]]:
    if process["timed_out"]:
        return ObservedOutcome.TIMED_OUT, {}
    signal_number = process["signal"]
    if signal_number is not None:
        try:
            name = signal.Signals(signal_number).name
        except ValueError:
            name = None
        return ObservedOutcome.CRASHED, {"signal_name": name}
    if process["output_exhausted"]:
        return ObservedOutcome.BUDGET_EXHAUSTED, {}
    if process["exit_code"] != 0:
        return ObservedOutcome.HARNESS_FAILED, {}
    try:
        response = _worker_response(stdout)
        return ObservedOutcome(response["observed"]), response["details"]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return ObservedOutcome.HARNESS_FAILED, {}


def run_case(
    run_dir: Path,
    request: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = 30.0,
    command: Sequence[str] | None = None,
    output_budget_bytes: int | None = None,
) -> CaseResult:
    root = run_dir.resolve()
    request_path = _relative(root, request)
    _relative(root, output_dir)
    payload = _request_payload(request_path)
    _relative(root, payload["manifest"])
    _relative(root, payload["artifact"])
    expectation = RobustnessExpectation(payload["expectation"])
    command = command or (
        sys.executable, "-m", "format_bench.robustness.worker", "--request", Path(request).as_posix()
    )
    process, stdout, stderr = _process(
        command, root, timeout_seconds, output_budget_bytes
    )
    stdout_path = _save(root, Path(output_dir) / "stdout.txt", stdout)
    stderr_path = _save(root, Path(output_dir) / "stderr.txt", stderr)
    observed, details = _outcome(process, stdout)
    verdict = robustness_verdict(expectation, observed)
    return {
        "case_id": payload["case_id"],
        "target": payload["target"],
        "expectation": expectation,
        "observed": observed,
        "verdict": verdict,
        "details": details,
        "process": process,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }
