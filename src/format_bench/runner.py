from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import random
import resource
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Callable, TypeVar


_Measured = TypeVar("_Measured")


@dataclass(frozen=True)
class MeasurementConfig:
    fresh_processes: int = 10
    fresh_workers: int = 1
    warmups: int = 5
    iterations: int = 30
    timeout_seconds: int = 120
    seed: int = 20260703


@dataclass(frozen=True)
class Job:
    job_id: str
    command: tuple[str, ...]
    expected_result: int


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("at least one timing sample is required")
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def stats_ms(values: list[float]) -> dict[str, float | int]:
    q1, q3 = percentile(values, 0.25), percentile(values, 0.75)
    return {
        "samples": len(values),
        "p50_ms": round(percentile(values, 0.50), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "q1_ms": round(q1, 3),
        "q3_ms": round(q3, 3),
        "iqr_ms": round(q3 - q1, 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
    }


def measure_callable(
    invoke: Callable[[], _Measured],
    expected: int,
    warmups: int,
    iterations: int,
    *,
    result_count: Callable[[_Measured], int] | None = None,
    validate: Callable[[_Measured], None] | None = None,
) -> dict:
    count = result_count or (lambda value: value)  # type: ignore[return-value]

    def check_result(value: _Measured) -> int:
        result = count(value)
        if result != expected:
            raise ValueError(
                f"unexpected operation result: expected {expected}, got {result}"
            )
        return result

    started = time.perf_counter_ns()
    first_value = invoke()
    first_open_ms = (time.perf_counter_ns() - started) / 1_000_000
    first_result = check_result(first_value)
    if validate is not None:
        validate(first_value)
    for _ in range(warmups):
        warmup_value = invoke()
        check_result(warmup_value)
        if validate is not None:
            validate(warmup_value)
    samples: list[float] = []
    result = first_result
    for _ in range(iterations):
        started = time.perf_counter_ns()
        value = invoke()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        result = check_result(value)
        if validate is not None:
            validate(value)
        samples.append(elapsed_ms)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        rss *= 1024
    return {
        "first_open_ms": first_open_ms,
        "samples_ms": samples,
        "result": result,
        "max_rss_bytes": int(rss),
    }


def _run_fresh_process(
    job: Job, config: MeasurementConfig, cwd: Path
) -> dict:
    env = {
        **os.environ,
        "FORMAT_BENCH_WARMUPS": str(config.warmups),
        "FORMAT_BENCH_ITERATIONS": str(config.iterations),
        "PYTHONHASHSEED": str(config.seed),
    }
    try:
        completed = subprocess.run(
            job.command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"status": "FAILED", "reason": "fresh worker timed out"}
    if completed.returncode != 0:
        return {
            "status": "FAILED",
            "reason": f"worker exited {completed.returncode}: {completed.stderr[-2000:]}",
        }
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        if not isinstance(result, dict):
            raise ValueError("worker JSON must be an object")
    except (json.JSONDecodeError, IndexError, ValueError) as error:
        return {
            "status": "FAILED",
            "reason": f"worker returned invalid JSON: {error}",
        }
    missing = sorted(
        field
        for field in ("first_open_ms", "samples_ms", "result", "max_rss_bytes")
        if field not in result
    )
    if missing:
        return {
            "status": "FAILED",
            "reason": f"worker response missing required fields: {', '.join(missing)}",
        }
    if (
        isinstance(result["result"], bool)
        or not isinstance(result["result"], int)
        or not isinstance(result["first_open_ms"], (int, float))
        or not isinstance(result["samples_ms"], list)
        or not all(isinstance(sample, (int, float)) for sample in result["samples_ms"])
        or not isinstance(result["max_rss_bytes"], int)
    ):
        return {"status": "FAILED", "reason": "worker response has invalid field types"}
    if result["result"] != job.expected_result:
        return {"status": "FAILED", "reason": "worker result count mismatch"}
    return result


def run_job(job: Job, config: MeasurementConfig, cwd: Path) -> dict:
    if config.fresh_workers <= 0:
        raise ValueError("fresh_workers must be positive")
    with ThreadPoolExecutor(
        max_workers=min(config.fresh_workers, config.fresh_processes)
    ) as executor:
        futures = [
            executor.submit(_run_fresh_process, job, config, cwd)
            for _ in range(config.fresh_processes)
        ]
        processes = [future.result() for future in futures]
    failed = next(
        (process for process in processes if process.get("status") == "FAILED"), None
    )
    if failed is not None:
        return failed

    evidence = processes[-1].get("evidence")
    if any(process.get("evidence") != evidence for process in processes):
        return {"status": "FAILED", "reason": "worker evidence changed between processes"}

    warm = [sample for process in processes for sample in process["samples_ms"]]
    first = [process["first_open_ms"] for process in processes]
    rss = [process["max_rss_bytes"] for process in processes]
    warm_process_p50 = [statistics.median(process["samples_ms"]) for process in processes]
    warm_process_p95 = [
        percentile(process["samples_ms"], 0.95) for process in processes
    ]
    return {
        "status": "MEASURED",
        "fresh_process": stats_ms(first),
        "warm": stats_ms(warm),
        "max_rss_bytes_p50": int(statistics.median(rss)),
        "fresh_samples_ms": first,
        "warm_samples_ms": warm,
        "warm_process_p50_ms": warm_process_p50,
        "warm_process_p95_ms": warm_process_p95,
        "result": processes[-1]["result"],
        "evidence": evidence,
    }


def parallel_worker_counts(job_count: int, *, parallel: bool) -> dict[str, int]:
    """Return the configured and effective worker counts for a job batch."""
    if job_count < 0:
        raise ValueError("job_count must be non-negative")
    if not parallel:
        return {"requested_workers": 1, "effective_workers": 1}
    requested_workers = int(os.environ.get("FORMAT_BENCH_MAX_WORKERS", "8"))
    if requested_workers <= 0:
        raise ValueError("FORMAT_BENCH_MAX_WORKERS must be positive")
    return {
        "requested_workers": requested_workers,
        "effective_workers": min(job_count, requested_workers),
    }


def run_jobs(
    jobs: list[Job],
    config: MeasurementConfig,
    cwd: Path,
    *,
    parallel: bool = False,
) -> dict[str, dict]:
    ordered = list(jobs)
    random.Random(config.seed).shuffle(ordered)
    if not ordered:
        return {}
    if not parallel:
        return {job.job_id: run_job(job, config, cwd) for job in ordered}
    worker_count = parallel_worker_counts(len(ordered), parallel=True)[
        "effective_workers"
    ]
    # Parallel mode is reserved for explicitly independent workloads; benchmark
    # lanes stay serial so measured formats do not contend for shared resources.
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            job.job_id: executor.submit(run_job, job, config, cwd) for job in ordered
        }
        return {job.job_id: futures[job.job_id].result() for job in ordered}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _linux_hardware_model() -> str:
    product = ""
    try:
        product = Path("/sys/devices/virtual/dmi/id/product_name").read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    except OSError:
        pass

    candidates = {"model name": "", "hardware": "", "model": ""}
    try:
        for line in Path("/proc/cpuinfo").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            key, separator, value = line.partition(":")
            normalized_key = key.strip().lower()
            if separator and normalized_key in candidates and not candidates[normalized_key]:
                candidates[normalized_key] = value.strip()
    except OSError:
        pass

    cpu = next(
        (candidates[key] for key in ("model name", "hardware", "model") if candidates[key]),
        "",
    )
    return " / ".join(dict.fromkeys(value for value in (product, cpu) if value))


def _hardware_model() -> str:
    if sys.platform == "darwin":
        probe = subprocess.run(
            ["sysctl", "-n", "hw.model"],
            text=True,
            capture_output=True,
            check=False,
        )
        model = probe.stdout.strip()
        if probe.returncode == 0 and model:
            return model
    if sys.platform.startswith("linux"):
        model = _linux_hardware_model()
        if model:
            return model
    processor = platform.processor().strip()
    machine = platform.machine().strip()
    return processor if processor and processor != machine else machine


def environment_info(root: Path) -> dict:
    packages = {}
    for name in (
        "pandas",
        "cbor2",
        "duckdb",
        "fastavro",
        "msgpack",
        "pyarrow",
        "pyfastlanes",
        "pylance",
        "pytz",
        "tiktoken",
        "tsfile",
        "tzdata",
        "vortex-data",
        "zstandard",
    ):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()
    return {
        "git_commit": commit,
        "flake_lock_sha256": _sha256(root / "flake.lock"),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "hardware_model": _hardware_model(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "packages": packages,
    }


def new_results(root: Path, run_id: str, config: MeasurementConfig) -> dict:
    return {
        "schema_version": "1",
        "run_id": run_id,
        "environment": environment_info(root),
        "measurement": measurement_metadata(config),
        "results": {},
    }


def measurement_metadata(config: MeasurementConfig) -> dict:
    return {
        **asdict(config),
        "worker_timeout_seconds": config.timeout_seconds,
        "os_cache_purged": False,
    }
