import subprocess
import sys


def test_fastlanes_claim_import_does_not_require_tsfile_dependencies() -> None:
    code = """
import sys
sys.modules["pyarrow"] = None
from format_bench.claims.fastlanes import run_fastlanes_claim
assert callable(run_fastlanes_claim)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
