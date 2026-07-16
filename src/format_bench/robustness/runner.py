from __future__ import annotations

import json
import hashlib
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NotRequired, Sequence, TypedDict, cast

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
    encoded = (json.dumps(details, indent=2, sort_keys=True) + "\n").encode()
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


def _append_tail(
    current: bytearray,
    data: bytes,
    budget: int | None,
) -> None:
    current.extend(data)
    if budget is None:
        return
    excess = len(current) - budget
    if excess > 0:
        del current[:excess]


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
    process = subprocess.Popen(
        list(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True, env=env,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_pipe, stderr_pipe = process.stdout, process.stderr
    stdout_tail = bytearray()
    stderr_tail = bytearray()
    stdout_bytes = 0
    stderr_bytes = 0
    timed_out = False
    cleanup_sent = False
    stdout_budget = (
        output_budget_bytes // 2 if output_budget_bytes is not None else None
    )
    stderr_budget = (
        output_budget_bytes - stdout_budget
        if output_budget_bytes is not None and stdout_budget is not None
        else None
    )

    def cleanup_group() -> None:
        nonlocal cleanup_sent
        if cleanup_sent:
            return
        cleanup_sent = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    try:
        os.set_blocking(stdout_pipe.fileno(), False)
        os.set_blocking(stderr_pipe.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(stdout_pipe, selectors.EVENT_READ, "stdout")
            selector.register(stderr_pipe, selectors.EVENT_READ, "stderr")
            deadline = time.monotonic() + timeout
            while selector.get_map() or process.poll() is None:
                if process.poll() is not None:
                    cleanup_group()
                elif time.monotonic() >= deadline:
                    timed_out = True
                    cleanup_group()

                if not selector.get_map():
                    if process.poll() is None:
                        time.sleep(0.01)
                    continue

                wait_for = 0.05
                if not cleanup_sent:
                    wait_for = max(0.0, min(wait_for, deadline - time.monotonic()))
                for key, _ in selector.select(wait_for):
                    try:
                        chunk = os.read(key.fd, 64 * 1024)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        (stdout_pipe if key.data == "stdout" else stderr_pipe).close()
                        continue
                    if key.data == "stdout":
                        stdout_bytes += len(chunk)
                        _append_tail(
                            stdout_tail, chunk, stdout_budget
                        )
                    else:
                        stderr_bytes += len(chunk)
                        _append_tail(
                            stderr_tail, chunk, stderr_budget
                        )
        process.wait()
    finally:
        if process.poll() is None:
            cleanup_group()
            process.wait()
        if not stdout_pipe.closed:
            stdout_pipe.close()
        if not stderr_pipe.closed:
            stderr_pipe.close()
    duration_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    stdout = bytes(stdout_tail).decode("utf-8", errors="ignore")
    stderr = bytes(stderr_tail).decode("utf-8", errors="ignore")
    return {
        "exit_code": process.returncode if not timed_out and process.returncode >= 0 else None,
        "signal": (
            -process.returncode
            if not timed_out and process.returncode is not None and process.returncode < 0
            else None
        ),
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "stdout_truncated": len(stdout_tail) < stdout_bytes,
        "stderr_truncated": len(stderr_tail) < stderr_bytes,
        "output_budget_bytes": output_budget_bytes,
        "output_exhausted": len(stdout_tail) + len(stderr_tail) < stdout_bytes + stderr_bytes,
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
