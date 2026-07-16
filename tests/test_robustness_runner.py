import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from format_bench.model import ObservedOutcome, RobustnessVerdict
from format_bench.robustness.runner import (
    DEFAULT_OUTPUT_RETENTION_BYTES,
    _process,
    run_case,
)


def _request(root: Path, expectation: str = "MUST_NOT_CRASH") -> None:
    (root / "input").mkdir(parents=True)
    (root / "input" / "manifest.json").write_text("{}")
    (root / "input" / "data.bin").write_bytes(b"data")
    (root / "request.json").write_text(json.dumps({
        "schema_version": "1", "contract_version": "1",
        "case_id": "case-1", "target": "csv",
        "expectation": expectation, "manifest": "input/manifest.json", "artifact": "input/data.bin",
    }))


def _run(
    tmp_path: Path,
    code: str,
    expectation: str = "MUST_NOT_CRASH",
    output_budget_bytes: int | None = None,
) -> dict:
    _request(tmp_path, expectation)
    return run_case(
        tmp_path, "request.json", "evidence/case-1", 0.2,
        (sys.executable, "-c", code), output_budget_bytes,
    )


def test_runner_classifies_normal_response_and_saves_streams(tmp_path: Path) -> None:
    code = "import json; print(json.dumps({'observed':'REJECTED','details':{'error_type':'Invalid'}}))"
    result = _run(tmp_path, code)
    assert result["observed"] is ObservedOutcome.REJECTED
    assert result["verdict"] is RobustnessVerdict.PASS
    assert (tmp_path / result["stdout"]).is_file()


def test_runner_classifies_signal_and_timeout(tmp_path: Path) -> None:
    crashed = _run(tmp_path / "crash", f"import os,signal; os.kill(os.getpid(), signal.{signal.SIGTERM.name})")
    assert crashed["observed"] is ObservedOutcome.CRASHED
    assert crashed["process"]["signal"] == signal.SIGTERM
    timed_out = _run(tmp_path / "timeout", "import time; time.sleep(5)")
    assert timed_out["observed"] is ObservedOutcome.TIMED_OUT
    assert timed_out["process"]["signal"] is None


def test_runner_classifies_timeout_after_bytes_output(tmp_path: Path) -> None:
    code = "import os,time; os.write(1,b'worker-bytes\\n'); time.sleep(5)"
    timed_out = _run(tmp_path, code)
    assert timed_out["observed"] is ObservedOutcome.TIMED_OUT
    assert timed_out["process"]["signal"] is None
    assert (tmp_path / timed_out["stdout"]).read_bytes() == b"worker-bytes\n"


def test_process_reaps_descendant_after_leader_exit(tmp_path: Path) -> None:
    pid_path = tmp_path / "descendant.pid"
    ready_path = tmp_path / "descendant.ready"
    descendant = (
        "from pathlib import Path; import os,time; "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
        f"Path({str(ready_path)!r}).write_text('ready'); "
        "print('DESCENDANT-TAIL', flush=True); time.sleep(30)"
    )
    leader = "\n".join(
        (
            "from pathlib import Path",
            "import subprocess,sys,time",
            f"subprocess.Popen([sys.executable, '-c', {descendant!r}], stdout=sys.stdout, stderr=sys.stderr)",
            f"ready=Path({str(ready_path)!r}); deadline=time.time()+2",
            "while not ready.exists() and time.time() < deadline:",
            "    time.sleep(0.01)",
            "print('LEADER-EXIT', flush=True)",
        )
    )
    process, stdout, _ = _process(
        (sys.executable, "-c", leader), tmp_path, 2, output_budget_bytes=256
    )
    pid = int(pid_path.read_text())
    try:
        assert process["exit_code"] == 0
        assert "DESCENDANT-TAIL" in stdout
        deadline = time.monotonic() + 1
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                pytest.fail("descendant survived process-group cleanup")
            time.sleep(0.01)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_process_bounds_drain_for_detached_descendant(tmp_path: Path) -> None:
    pid_path = tmp_path / "detached.pid"
    descendant = (
        "from pathlib import Path; import os,time; os.setsid(); "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
        "print('DETACHED-TAIL', flush=True); time.sleep(30)"
    )
    leader = "\n".join(
        (
            "from pathlib import Path",
            "import subprocess,sys,time",
            f"subprocess.Popen([sys.executable, '-c', {descendant!r}], stdout=sys.stdout, stderr=sys.stderr)",
            f"path=Path({str(pid_path)!r}); deadline=time.time()+2",
            "while not path.exists() and time.time() < deadline:",
            "    time.sleep(0.01)",
        )
    )
    started = time.monotonic()
    process, stdout, _ = _process(
        (sys.executable, "-c", leader), tmp_path, 2, output_budget_bytes=256
    )
    pid = int(pid_path.read_text())
    try:
        assert process["timed_out"] is True
        assert process["signal"] is None
        assert process["cleanup_incomplete"] is True
        assert time.monotonic() - started < 3
        assert "DETACHED-TAIL" in stdout
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_runner_classifies_invalid_output_and_valid_roundtrip_failure(tmp_path: Path) -> None:
    invalid = _run(tmp_path / "invalid", "print('partial')")
    assert invalid["observed"] is ObservedOutcome.HARNESS_FAILED
    wrong_shape = _run(
        tmp_path / "wrong-shape",
        "import json; print(json.dumps({'observed': 7, 'details': []}))",
    )
    assert wrong_shape["observed"] is ObservedOutcome.HARNESS_FAILED
    large_details = _run(
        tmp_path / "large-details",
        "import json; print(json.dumps({'observed':'REJECTED','details':{'message':'x'*10000}}))",
    )
    assert large_details["details"]["truncated"] is True
    assert large_details["details"]["original_size_bytes"] > 4096
    valid = _run(tmp_path / "valid", "import json; print(json.dumps({'observed':'REJECTED'}))", "MUST_ROUNDTRIP")
    assert valid["verdict"] is RobustnessVerdict.FAIL


def test_runner_bounds_deep_worker_details_without_escaping(tmp_path: Path) -> None:
    code = (
        "depth=1000; "
        "payload='{" + '\"observed\":\"REJECTED\",\"details\":' + "' "
        "+ '{\"nested\":' * depth + '0' + '}' * depth + '}'"
        "; print(payload)"
    )
    result = _run(tmp_path, code)
    assert result["observed"] is ObservedOutcome.REJECTED
    assert result["verdict"] is RobustnessVerdict.PASS
    assert result["details"] == {
        "truncated": True,
        "error_type": "RecursionError",
    }


def test_runner_reuses_unused_stream_budget(tmp_path: Path) -> None:
    code = "import json; print(json.dumps({'observed':'REJECTED','details':{'message':'x'*200}}))"
    result = _run(tmp_path, code, output_budget_bytes=512)
    assert result["observed"] is ObservedOutcome.REJECTED
    assert result["process"]["output_exhausted"] is False


def test_runner_bounds_retained_output_without_explicit_budget(tmp_path: Path) -> None:
    code = "import sys; print('O'*({size}), file=sys.stdout); print('E'*({size}), file=sys.stderr)".format(
        size=DEFAULT_OUTPUT_RETENTION_BYTES
    )
    process, stdout, stderr = _process(
        (sys.executable, "-c", code), tmp_path, 2
    )
    assert process["output_budget_bytes"] == DEFAULT_OUTPUT_RETENTION_BYTES
    assert process["output_exhausted"] is True
    assert process["stdout_truncated"] is True
    assert process["stderr_truncated"] is True
    assert len(stdout.encode()) + len(stderr.encode()) <= DEFAULT_OUTPUT_RETENTION_BYTES


def test_runner_drains_noisy_child_beyond_pipe_capacity(tmp_path: Path) -> None:
    code = "\n".join(
        (
            "import os",
            "chunk_out=b'O'*65536; chunk_err=b'E'*65536",
            "for _ in range(64):",
            "    os.write(1, chunk_out)",
            "    os.write(2, chunk_err)",
        )
    )
    process, stdout, stderr = _process(
        (sys.executable, "-c", code), tmp_path, 2, output_budget_bytes=256
    )
    assert process["exit_code"] == 0
    assert process["timed_out"] is False
    assert process["stdout_bytes"] > 1_000_000
    assert process["stderr_bytes"] > 1_000_000
    assert process["output_exhausted"] is True
    assert len(stdout.encode()) + len(stderr.encode()) <= 256


def test_runner_rejects_unsafe_request_paths(tmp_path: Path) -> None:
    _request(tmp_path)
    with pytest.raises(ValueError, match="safe relative"):
        run_case(tmp_path, "../request.json", "evidence")


def test_runner_rejects_invalid_request_field_types(tmp_path: Path) -> None:
    _request(tmp_path)
    request = json.loads((tmp_path / "request.json").read_text())
    request["manifest"] = 7
    (tmp_path / "request.json").write_text(json.dumps(request))
    with pytest.raises(TypeError, match="manifest must be a string"):
        run_case(tmp_path, "request.json", "evidence/case-1")


def test_runner_rejects_symlinks_inside_directory_artifacts(tmp_path: Path) -> None:
    _request(tmp_path)
    artifact = tmp_path / "artifact.lance"
    artifact.mkdir()
    (artifact / "data.bin").write_bytes(b"data")
    (artifact / "link").symlink_to(tmp_path / "outside")
    request = json.loads((tmp_path / "request.json").read_text())
    request["artifact"] = "artifact.lance"
    (tmp_path / "request.json").write_text(json.dumps(request))
    with pytest.raises(ValueError, match="symlink"):
        run_case(tmp_path, "request.json", "evidence/case-1")


def test_runner_revalidates_output_path_after_worker_execution(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    code = (
        "import json; from pathlib import Path; "
        "path=Path('evidence/case-1'); path.parent.mkdir(parents=True); "
        f"path.symlink_to({str(outside)!r}, target_is_directory=True); "
        "print(json.dumps({'observed':'REJECTED','details':{}}))"
    )

    with pytest.raises(ValueError, match="symlink"):
        _run(tmp_path, code)

    assert not (outside / "stdout.txt").exists()
    assert not (outside / "stderr.txt").exists()


def test_runner_rejects_preexisting_hard_link_evidence(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("unchanged")
    code = (
        "import json,os; from pathlib import Path; "
        "path=Path('evidence/case-1'); path.mkdir(parents=True); "
        f"os.link({str(outside)!r}, path/'stdout.txt'); "
        "print(json.dumps({'observed':'REJECTED','details':{}}))"
    )

    with pytest.raises(FileExistsError):
        _run(tmp_path, code)

    assert outside.read_text() == "unchanged"


def test_runner_exposes_source_package_to_child(tmp_path: Path) -> None:
    process, stdout, _ = _process(
        (sys.executable, "-c", "import format_bench; print(format_bench.__name__)"),
        tmp_path,
        1,
    )
    assert process["exit_code"] == 0
    assert stdout.strip() == "format_bench"


def test_runner_bounds_streams_and_preserves_diagnostic_tails(tmp_path: Path) -> None:
    code = (
        "import sys; "
        "print('A'*200 + 'OUT-TAIL'); "
        "print('B'*200 + 'ERR-TAIL', file=sys.stderr)"
    )
    result = _run(tmp_path, code, output_budget_bytes=80)
    process = result["process"]
    assert result["observed"] is ObservedOutcome.BUDGET_EXHAUSTED
    assert result["verdict"] is RobustnessVerdict.INCOMPLETE
    assert process["output_exhausted"] is True
    assert process["stdout_bytes"] > 80 and process["stderr_bytes"] > 80
    stdout = (tmp_path / result["stdout"]).read_text()
    stderr = (tmp_path / result["stderr"]).read_text()
    assert len(stdout.encode()) + len(stderr.encode()) <= 80
    assert stdout.rstrip().endswith("OUT-TAIL")
    assert stderr.rstrip().endswith("ERR-TAIL")


def test_noisy_signal_keeps_crash_precedence(tmp_path: Path) -> None:
    code = (
        "import os,signal; print('x'*1000, flush=True); "
        f"os.kill(os.getpid(), signal.{signal.SIGTERM.name})"
    )
    result = _run(tmp_path, code, output_budget_bytes=16)
    assert result["observed"] is ObservedOutcome.CRASHED
    assert result["process"]["output_exhausted"] is True
