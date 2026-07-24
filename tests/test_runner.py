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
    measurement_metadata,
    parallel_worker_counts,
    run_job,
    run_jobs,
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


def test_measure_callable_excludes_validation_from_timing(monkeypatch) -> None:
    ticks = iter(
        [
            0,
            1_000_000,
            1_001_000_000,
            2_001_000_000,
            2_002_000_000,
            3_002_000_000,
        ]
    )
    monkeypatch.setattr(runner.time, "perf_counter_ns", lambda: next(ticks))

    def validate(_value: int) -> None:
        runner.time.perf_counter_ns()

    measured = measure_callable(
        lambda: 3,
        expected=3,
        warmups=0,
        iterations=1,
        validate=validate,
    )

    assert measured["first_open_ms"] == 1.0
    assert measured["samples_ms"] == [1.0]


def test_parallel_worker_counts_include_environment_cap(monkeypatch) -> None:
    monkeypatch.setenv("FORMAT_BENCH_MAX_WORKERS", "8")

    assert parallel_worker_counts(3, parallel=True) == {
        "requested_workers": 8,
        "effective_workers": 3,
    }


def test_measurement_metadata_defines_data_and_timing_estimands() -> None:
    measurement = measurement_metadata(
        MeasurementConfig(),
        dataset_id="fixture",
        dataset_manifest={"rows": 4, "source_sha256": "a" * 64},
    )
    estimand = measurement["estimand"]

    assert estimand["target_population"] == {
        "kind": "immutable_dataset_snapshot",
        "dataset_id": "fixture",
        "membership": "all_declared_rows",
        "rows": 4,
        "source_sha256": "a" * 64,
    }
    assert estimand["timing_population"]["unit"] == "fresh_child_process"
    assert estimand["targets"]["fresh_p50_ms"]["evidence_field"] == "fresh_samples_ms"
    assert estimand["targets"]["fresh_p50_ms"]["variable"] == (
        "first_invocation_elapsed_excluding_validation"
    )
    assert estimand["targets"]["warm_p50_ms"]["estimator"] == (
        "median_of_per_process_medians"
    )
    assert estimand["targets"]["warm_p50_ms"]["evidence_field"] == (
        "warm_process_p50_ms"
    )
    assert estimand["targets"]["warm_p95_ms"]["evidence_field"] == (
        "warm_process_p95_ms"
    )
    assert estimand["descriptive_outputs"]["warm"].startswith("pooled_iterations")
    assert estimand["failure_strategy"].endswith("without_imputation")


@pytest.mark.parametrize(
    "dataset_manifest",
    [
        {"rows": True, "source_sha256": "a" * 64},
        {"rows": -1, "source_sha256": "a" * 64},
        {"rows": 4, "source_sha256": ""},
        {"rows": 4, "source_sha256": "not-a-sha256"},
    ],
)
def test_measurement_metadata_rejects_invalid_population(
    dataset_manifest: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="estimand"):
        measurement_metadata(
            MeasurementConfig(),
            dataset_id="fixture",
            dataset_manifest=dataset_manifest,
        )


@pytest.mark.parametrize("dataset_id", [123, "../fixture"])
def test_measurement_metadata_rejects_invalid_dataset_id(dataset_id: object) -> None:
    with pytest.raises(ValueError, match="estimand"):
        measurement_metadata(
            MeasurementConfig(),
            dataset_id=dataset_id,
            dataset_manifest={"rows": 4, "source_sha256": "a" * 64},
        )


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
            "evidence": {"normalized_hash": "fixture"},
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
    assert result["warm_process_estimates"] == {
        "median_p50_ms": 1.25,
        "median_p95_ms": 1.475,
    }


@pytest.mark.parametrize("samples", [[], [1.0, 2.0], [-1.0]])
def test_run_job_rejects_malformed_timing_samples(
    tmp_path: Path, samples: list[float]
) -> None:
    payload = json.dumps(
        {
            "first_open_ms": 2.0,
            "samples_ms": samples,
            "result": 7,
            "max_rss_bytes": 100,
            "evidence": {"normalized_hash": "fixture"},
        }
    )
    job = Job("fixture/read", (sys.executable, "-c", f"print({payload!r})"), 7)

    result = run_job(
        job,
        MeasurementConfig(fresh_processes=1, warmups=0, iterations=1),
        tmp_path,
    )

    assert result["status"] == "FAILED"
    assert "timing" in result["reason"]


def test_run_job_rejects_missing_result_evidence(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "first_open_ms": 2.0,
            "samples_ms": [1.0],
            "result": 7,
            "max_rss_bytes": 100,
        }
    )
    job = Job("fixture/read", (sys.executable, "-c", f"print({payload!r})"), 7)

    result = run_job(
        job,
        MeasurementConfig(fresh_processes=1, warmups=0, iterations=1),
        tmp_path,
    )

    assert result["status"] == "FAILED"
    assert "evidence" in result["reason"]


def test_run_jobs_records_unexpected_job_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_unexpected(*_args, **_kwargs):
        raise RuntimeError("fixture crash")

    monkeypatch.setattr(runner, "run_job", raise_unexpected)
    job = Job("fixture/read", ("fixture",), 7)

    assert run_jobs([job], MeasurementConfig(), tmp_path) == {
        "fixture/read": {
            "status": "FAILED",
            "reason": "RuntimeError: fixture crash",
        }
    }


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


def test_run_job_joins_running_fresh_attempts_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    barrier = threading.Barrier(2)
    release_running = threading.Event()
    failure_ready = threading.Event()
    running_finished = threading.Event()
    roles = iter(("failure", "running"))
    roles_lock = threading.Lock()

    def fake_run_fresh_process(job, config, cwd):
        with roles_lock:
            role = next(roles)
        barrier.wait(timeout=2)
        if role == "failure":
            failure_ready.set()
            return {"status": "FAILED", "reason": "first failure"}
        release_running.wait(timeout=2)
        running_finished.set()
        return {"status": "FAILED", "reason": "later failure"}

    monkeypatch.setattr(runner, "_run_fresh_process", fake_run_fresh_process)
    job = Job("fixture/read", ("fixture",), 7)
    result_holder: list[dict] = []
    returned = threading.Event()

    def invoke() -> None:
        result_holder.append(
            run_job(
                job,
                MeasurementConfig(fresh_processes=2, fresh_workers=2),
                tmp_path,
            )
        )
        returned.set()

    thread = threading.Thread(target=invoke)
    thread.start()
    try:
        assert failure_ready.wait(timeout=2)
        assert not returned.wait(timeout=0.1)
        assert not running_finished.is_set()
    finally:
        release_running.set()
        thread.join(timeout=2)

    assert not thread.is_alive()
    assert running_finished.is_set()
    assert result_holder == [{"status": "FAILED", "reason": "first failure"}]


def test_run_job_classifies_invalid_worker_output_as_failure(tmp_path: Path) -> None:
    job = Job("fixture/read", (sys.executable, "-c", "print('not json')"), 7)
    result = run_job(job, MeasurementConfig(fresh_processes=1), tmp_path)
    assert result["status"] == "FAILED"
    assert "invalid JSON" in result["reason"]


def test_run_job_rejects_nonfinite_worker_output(tmp_path: Path) -> None:
    job = Job(
        "fixture/read",
        (sys.executable, "-c", "print('{\"first_open_ms\":NaN}')"),
        7,
    )
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
