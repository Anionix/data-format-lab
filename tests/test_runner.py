import json
import sys
import threading
import time
from pathlib import Path

import pytest

import format_bench.runner as runner
from format_bench.runner import (
    Job,
    MeasurementConfig,
    environment_info,
    measure_callable,
    parallel_worker_counts,
    run_job,
    stats_ms,
)


def test_stats_include_distribution_and_iqr() -> None:
    stats = stats_ms([5.0, 1.0, 3.0, 2.0, 4.0])
    assert stats["p50_ms"] == 3.0
    assert stats["p95_ms"] == 4.8
    assert stats["iqr_ms"] == 2.0


def test_measure_callable_validates_result_count() -> None:
    measured = measure_callable(lambda: 3, expected=3, warmups=1, iterations=2)
    assert measured["result"] == 3
    assert len(measured["samples_ms"]) == 2
    with pytest.raises(ValueError, match="unexpected operation result"):
        measure_callable(lambda: 2, expected=3, warmups=0, iterations=1)


def test_parallel_worker_counts_include_environment_cap(monkeypatch) -> None:
    monkeypatch.setenv("FORMAT_BENCH_MAX_WORKERS", "8")

    assert parallel_worker_counts(3, parallel=True) == {
        "requested_workers": 8,
        "effective_workers": 3,
    }


@pytest.mark.parametrize(
    ("values", "warmups", "iterations"),
    [([3, 2, 3], 1, 1), ([3, 3, 2, 3], 0, 3)],
)
def test_measure_callable_rejects_any_intermediate_mismatch(
    values: list[int], warmups: int, iterations: int
) -> None:
    results = iter(values)
    with pytest.raises(ValueError, match="unexpected operation result"):
        measure_callable(lambda: next(results), 3, warmups, iterations)


def test_run_job_aggregates_fresh_process_output(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "first_open_ms": 2.0,
            "samples_ms": [1.0, 1.5],
            "result": 7,
            "max_rss_bytes": 100,
        }
    )
    job = Job("fixture/read", (sys.executable, "-c", f"print({payload!r})"), 7)
    result = run_job(
        job,
        MeasurementConfig(
            fresh_processes=2, fresh_workers=2, warmups=0, iterations=2
        ),
        tmp_path,
    )
    assert result["status"] == "MEASURED"
    assert result["fresh_process"]["samples"] == 2
    assert result["warm"]["samples"] == 4
    assert result["max_rss_bytes_p50"] == 100


def test_run_job_stops_after_first_failed_fresh_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    release_second = threading.Event()

    def fake_run_fresh_process(job, config, cwd):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": "FAILED", "reason": "fixture timeout"}
        release_second.wait(timeout=2)
        return {"status": "FAILED", "reason": "later failure"}

    monkeypatch.setattr(runner, "_run_fresh_process", fake_run_fresh_process)
    job = Job("fixture/read", ("fixture",), 7)

    result_holder: list[dict] = []
    thread = threading.Thread(
        target=lambda: result_holder.append(
            run_job(
                job,
                MeasurementConfig(fresh_processes=4, fresh_workers=1),
                tmp_path,
            )
        )
    )
    started = time.monotonic()
    thread.start()
    thread.join(timeout=0.5)
    elapsed = time.monotonic() - started
    release_second.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert elapsed < 0.5
    assert result_holder == [{"status": "FAILED", "reason": "fixture timeout"}]


def test_run_job_classifies_invalid_worker_output_as_failure(tmp_path: Path) -> None:
    job = Job("fixture/read", (sys.executable, "-c", "print('not json')"), 7)
    result = run_job(job, MeasurementConfig(fresh_processes=1), tmp_path)
    assert result["status"] == "FAILED"
    assert "invalid JSON" in result["reason"]


def test_run_job_classifies_incomplete_worker_output_as_failure(tmp_path: Path) -> None:
    job = Job("fixture/read", (sys.executable, "-c", "print('{}')"), 7)
    result = run_job(job, MeasurementConfig(fresh_processes=1), tmp_path)
    assert result["status"] == "FAILED"
    assert "missing required fields" in result["reason"]


def test_environment_records_isolated_claim_dependencies() -> None:
    packages = environment_info(Path(__file__).parents[1])["packages"]
    assert {"pandas", "pytz", "tsfile", "tzdata"} <= packages.keys()


def test_environment_records_concrete_hardware_identity() -> None:
    environment = environment_info(Path(__file__).parents[1])
    assert isinstance(environment["hardware_model"], str)
    assert environment["hardware_model"]


def test_linux_hardware_identity_reads_product_and_cpu(monkeypatch) -> None:
    monkeypatch.setattr(runner.sys, "platform", "linux")

    def read_text(path: Path, *args, **kwargs) -> str:
        if str(path) == "/sys/devices/virtual/dmi/id/product_name":
            return "Virtual Machine\n"
        if str(path) == "/proc/cpuinfo":
            return (
                "processor : 0\n"
                "model : 79\n"
                "model name : AMD EPYC 7763 64-Core Processor\n"
            )
        raise FileNotFoundError(path)

    monkeypatch.setattr(runner.Path, "read_text", read_text)

    assert runner._hardware_model() == (
        "Virtual Machine / AMD EPYC 7763 64-Core Processor"
    )
