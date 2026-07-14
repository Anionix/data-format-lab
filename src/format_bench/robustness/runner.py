from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from format_bench.model import (
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
    robustness_verdict,
)
from format_bench.robustness.paths import reject_symlink_tree


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


def _save(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", errors="replace")
    return path.relative_to(path.parents[2]).as_posix()


def _process(command: Sequence[str], cwd: Path, timeout: float) -> tuple[dict, str, str]:
    started = time.perf_counter_ns()
    env = os.environ.copy()
    source_root = str(Path(__file__).parents[2])
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (source_root, env.get("PYTHONPATH")) if item
    )
    process = subprocess.Popen(
        list(command), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True, env=env,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        stdout = (error.stdout or "") + stdout
        stderr = (error.stderr or "") + stderr
    duration_ms = round((time.perf_counter_ns() - started) / 1_000_000, 3)
    return {
        "exit_code": process.returncode if not timed_out else None,
        "signal": -process.returncode if process.returncode is not None and process.returncode < 0 else None,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
    }, stdout, stderr


def _outcome(process: dict, stdout: str) -> tuple[ObservedOutcome, dict]:
    if process["timed_out"]:
        return ObservedOutcome.TIMED_OUT, {}
    if process["signal"] is not None:
        try:
            name = signal.Signals(process["signal"]).name
        except ValueError:
            name = None
        return ObservedOutcome.CRASHED, {"signal_name": name}
    if process["exit_code"] != 0:
        return ObservedOutcome.HARNESS_FAILED, {}
    try:
        response = json.loads(stdout.strip())
        return ObservedOutcome(response["observed"]), response.get("details", {})
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return ObservedOutcome.HARNESS_FAILED, {}


def run_case(
    run_dir: Path,
    request: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = 30.0,
    command: Sequence[str] | None = None,
) -> dict:
    root = run_dir.resolve()
    request_path = _relative(root, request)
    output_path = _relative(root, output_dir)
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    _relative(root, payload["manifest"])
    _relative(root, payload["artifact"])
    expectation = RobustnessExpectation(payload["expectation"])
    command = command or (
        sys.executable, "-m", "format_bench.robustness.worker", "--request", Path(request).as_posix()
    )
    process, stdout, stderr = _process(command, root, timeout_seconds)
    stdout_path = output_path / "stdout.txt"
    stderr_path = output_path / "stderr.txt"
    _save(stdout_path, stdout)
    _save(stderr_path, stderr)
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
        "stdout": stdout_path.relative_to(root).as_posix(),
        "stderr": stderr_path.relative_to(root).as_posix(),
    }
