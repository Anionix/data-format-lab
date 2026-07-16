from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/benchmark-fastlanes.yml"


def test_fastlanes_retry_workflow_is_pinned_and_linux_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "runs-on: ubuntu-24.04" in workflow
    assert "f0edc1020a538f1f8098640fce8347c9ac247a0d" in workflow
    assert "uv sync --frozen" in workflow
    assert "native/fastlanes/.venv/bin/python -m pip install" in workflow
    assert "run_fastlanes_claim" in workflow
    assert "mixed 13-column outcome" in workflow
    assert "timeout-minutes: 30" in workflow
    assert 'default: "120"' in workflow
    assert "timeout_seconds must be between 1 and 120" in workflow
    assert "tar --zstd" in workflow
    assert "retention-days: 14" in workflow

    assert workflow.index("name: Check out public commit") < workflow.index(
        "name: Initialize evidence directory"
    )


def test_fastlanes_retry_workflow_preserves_build_and_measurement_logs() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert '"$RUN_DIR/build.log"' in workflow
    assert '"$RUN_DIR/build-status.txt"' in workflow
    assert '"$RUN_DIR/measure.log"' in workflow
    assert '"$RUN_DIR/measure-error.txt"' in workflow
    assert '"$RUN_DIR/measure-status.txt"' in workflow
    assert "steps.measure.outcome" in workflow
    assert '"status": "UNSUPPORTED" if not available else "FAILED"' in workflow
    assert "case_hash_algorithm" in workflow
    assert "input/data.csv" in workflow
    assert "if: always()" in workflow
