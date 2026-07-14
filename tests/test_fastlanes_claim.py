import json
import subprocess
from pathlib import Path

from format_bench.claims.fastlanes import _run_case
from format_bench.claims.fastlanes_worker import _input
from format_bench.model import ObservedOutcome


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
    def crashed(*args, **kwargs):
        return subprocess.CompletedProcess(args, -11, "", "")

    monkeypatch.setattr(subprocess, "run", crashed)

    result = _run_case(tmp_path, "comma-malformed", 1024, 1)

    assert result["outcome"] is ObservedOutcome.CRASHED
    assert result["signal_name"] == "SIGSEGV"
    assert (tmp_path / "comma-malformed" / "stderr.txt").is_file()
