import json
import subprocess
import sys
from pathlib import Path

import pytest

from format_bench.claims.fastlanes import _fatal_cases, _run_case
from format_bench.claims import fastlanes_worker
from format_bench.claims.fastlanes_worker import MIXED_COLUMNS, _input
from format_bench.model import ObservedOutcome


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        (b"partial stdout: \xff", b"partial stderr: \xfe"),
        ("partial stdout", "partial stderr"),
    ],
)
def test_fastlanes_timeout_output_is_persisted_as_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str | bytes,
    stderr: str | bytes,
) -> None:
    def time_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            args[0], kwargs["timeout"], output=stdout, stderr=stderr
        )

    monkeypatch.setattr(subprocess, "run", time_out)

    result = _run_case(tmp_path, "mixed-13-columns", 1024, 1)

    expected_stdout = (
        stdout.decode("utf-8", errors="replace")
        if isinstance(stdout, bytes)
        else stdout
    )
    expected_stderr = (
        stderr.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes)
        else stderr
    )
    assert result["outcome"] is ObservedOutcome.TIMED_OUT
    assert (tmp_path / "mixed-13-columns" / "stdout.txt").read_text() == expected_stdout
    assert (tmp_path / "mixed-13-columns" / "stderr.txt").read_text() == expected_stderr


def test_fastlanes_input_contract_uses_pipe_and_pinned_schema(tmp_path: Path) -> None:
    schema, csv_path, data = _input(tmp_path, "numeric", 2)

    assert json.loads(schema.read_text()) == {
        "columns": [
            {"name": f"col{index}", "nullability": "NULL", "type": "integer"}
            for index in range(8)
        ]
    }
    assert data == b"0|1|2|3|4|5|6|7\n1|2|3|4|5|6|7|8\n"
    assert csv_path.read_bytes() == data


def test_fastlanes_runner_contains_native_crash(tmp_path: Path, monkeypatch) -> None:
    observed = {}

    def crashed(*args, **kwargs):
        command = args[0]
        observed["output"] = Path(command[command.index("--output") + 1])
        observed["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(args, -11, "", "")

    monkeypatch.setattr(subprocess, "run", crashed)

    result = _run_case(tmp_path, "comma-malformed", 1024, 1)

    assert result["outcome"] is ObservedOutcome.CRASHED
    assert result["signal_name"] == "SIGSEGV"
    assert observed["output"].is_absolute()
    assert observed["cwd"].is_absolute()
    assert (tmp_path / "comma-malformed" / "stderr.txt").is_file()


def test_fastlanes_mixed_input_matches_the_13_column_contract(tmp_path: Path) -> None:
    schema, csv_path, data = _input(tmp_path, "mixed", 2)
    payload = json.loads(schema.read_text())

    assert payload["columns"] == list(MIXED_COLUMNS)
    assert len(data.splitlines()[0].split(b"|")) == 13
    assert csv_path.read_bytes() == data


def test_fastlanes_worker_failure_is_classified_as_target_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, '{"failure_class":"TARGET","status":"FAILED"}\n', ""
        ),
    )

    result = _run_case(tmp_path, "mixed-13-columns", 1024, 1)

    assert result["status"] == "FAILED"
    assert result["outcome"] is ObservedOutcome.TARGET_FAILED


def test_fastlanes_worker_harness_failure_is_not_target_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args, 0, '{"failure_class":"HARNESS","status":"FAILED"}\n', ""
        ),
    )

    result = _run_case(tmp_path, "mixed-13-columns", 1024, 1)

    assert result["outcome"] is ObservedOutcome.HARNESS_FAILED


def test_fastlanes_invalid_worker_output_remains_a_harness_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "not-json\n", ""),
    )

    result = _run_case(tmp_path, "mixed-13-columns", 1024, 1)

    assert result["outcome"] is ObservedOutcome.HARNESS_FAILED


def test_fastlanes_nonfinite_worker_output_remains_a_harness_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            '{"failure_class":"TARGET","status":"FAILED","value":NaN}\n',
            "",
        ),
    )

    result = _run_case(tmp_path, "mixed-13-columns", 1024, 1)

    assert result["outcome"] is ObservedOutcome.HARNESS_FAILED


def test_fastlanes_worker_protocol_marks_target_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def raise_target(*args, **kwargs):
        raise fastlanes_worker.TargetFailure("target error", cause_type="RuntimeError")

    monkeypatch.setattr(
        fastlanes_worker,
        "run",
        raise_target,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["worker", "--case", "mixed", "--rows", "1", "--output", str(tmp_path)],
    )

    fastlanes_worker.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["failure_class"] == "TARGET"
    assert payload["error_type"] == "TargetFailure"
    assert payload["cause_type"] == "RuntimeError"


def test_fastlanes_worker_protocol_marks_harness_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    def raise_harness(*args, **kwargs):
        raise OSError("harness error")

    monkeypatch.setattr(
        fastlanes_worker,
        "run",
        raise_harness,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["worker", "--case", "mixed", "--rows", "1", "--output", str(tmp_path)],
    )

    fastlanes_worker.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["failure_class"] == "HARNESS"


def test_fastlanes_numeric_failure_is_fatal() -> None:
    numeric = {"case": "numeric", "outcome": ObservedOutcome.CRASHED}

    assert _fatal_cases(numeric) == [numeric]


def test_fastlanes_robustness_failures_do_not_change_claims_verdict() -> None:
    numeric = {"outcome": ObservedOutcome.ROUNDTRIP_EQUAL}
    strings = {"1023": {"status": "FAILED"}}
    malformed = {"outcome": ObservedOutcome.CRASHED}

    assert _fatal_cases(numeric) == []
    assert strings["1023"]["status"] == "FAILED"
    assert malformed["outcome"] is ObservedOutcome.CRASHED


def test_fastlanes_mixed_failure_is_fatal() -> None:
    numeric = {"outcome": ObservedOutcome.ROUNDTRIP_EQUAL}
    mixed = {"outcome": ObservedOutcome.TARGET_FAILED}

    assert _fatal_cases(numeric, mixed) == [mixed]


def test_fastlanes_skipped_numeric_control_does_not_fail_mixed_scope() -> None:
    numeric = {"case": "numeric-8-columns", "status": "SKIPPED"}
    mixed = {"outcome": ObservedOutcome.ROUNDTRIP_EQUAL}

    assert _fatal_cases(numeric, mixed) == []
