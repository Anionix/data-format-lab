import json
import signal
import sys
from pathlib import Path

import pytest

from format_bench.model import ObservedOutcome, RobustnessVerdict
from format_bench.robustness.runner import _process, run_case


def _request(root: Path, expectation: str = "MUST_NOT_CRASH") -> None:
    (root / "input").mkdir(parents=True)
    (root / "input" / "manifest.json").write_text("{}")
    (root / "input" / "data.bin").write_bytes(b"data")
    (root / "request.json").write_text(json.dumps({
        "schema_version": "1", "case_id": "case-1", "target": "csv",
        "expectation": expectation, "manifest": "input/manifest.json", "artifact": "input/data.bin",
    }))


def _run(tmp_path: Path, code: str, expectation: str = "MUST_NOT_CRASH") -> dict:
    _request(tmp_path, expectation)
    return run_case(tmp_path, "request.json", "evidence/case-1", 0.2, (sys.executable, "-c", code))


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


def test_runner_classifies_invalid_output_and_valid_roundtrip_failure(tmp_path: Path) -> None:
    invalid = _run(tmp_path / "invalid", "print('partial')")
    assert invalid["observed"] is ObservedOutcome.HARNESS_FAILED
    valid = _run(tmp_path / "valid", "import json; print(json.dumps({'observed':'REJECTED'}))", "MUST_ROUNDTRIP")
    assert valid["verdict"] is RobustnessVerdict.FAIL


def test_runner_rejects_unsafe_request_paths(tmp_path: Path) -> None:
    _request(tmp_path)
    with pytest.raises(ValueError, match="safe relative"):
        run_case(tmp_path, "../request.json", "evidence")


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


def test_runner_exposes_source_package_to_child(tmp_path: Path) -> None:
    process, stdout, _ = _process(
        (sys.executable, "-c", "import format_bench; print(format_bench.__name__)"),
        tmp_path,
        1,
    )
    assert process["exit_code"] == 0
    assert stdout.strip() == "format_bench"
