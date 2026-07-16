from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/benchmark-native.yml"


def test_native_workflow_runs_each_available_target_with_evidence_budget() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    targets = (
        "arrow-csv-fuzz",
        "parquet-arrow-fuzz",
        "parquet-encoding-fuzz",
        "vortex-file-io",
        "vortex-compress-roundtrip",
        "fastlanes-quick-fuzz",
        "lance",
        "object-jsonl",
        "tsfile",
    )
    assert all(workflow.count(f"- {target}\n") == 1 for target in targets)
    assert "max-parallel: 6" in workflow
    assert "--artifact-budget-mib 1024" in workflow
    assert "--target \"$TARGET\"" in workflow
    assert '--duration-seconds "$REQUESTED_DURATION_SECONDS"' in workflow
    assert "cd native/vortex && cargo fuzz build file_io" in workflow
    assert "cd native/vortex && cargo fuzz build compress_roundtrip" in workflow
    assert 'test "$REQUESTED_DURATION_SECONDS" -gt 3300' in workflow
    assert "timeout-minutes: 90" in workflow
    assert "retention-days: 14" in workflow
    assert "FALLBACK_DIR" in workflow
    assert "FALLBACK_TMP_DIR" in workflow
    assert "runner.temp" not in workflow
    assert "fallback/native-" in workflow
    assert "if: always()" in workflow
    assert "linux-x86_64" in workflow


def test_native_workflow_keeps_the_native_runner_failure_after_upload() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "id: native_source" in workflow
    assert "id: checkout" in workflow
    assert "id: native_build" in workflow
    assert "id: native" in workflow
    assert "continue-on-error: true" in workflow
    assert "steps.native_source.outcome" in workflow
    assert "steps.native_build.outcome" in workflow
    assert "steps.native.outcome" in workflow
    assert "steps.evidence.outcome" in workflow
    assert '"TARGET_FAILED"' in workflow
