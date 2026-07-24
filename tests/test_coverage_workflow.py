from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github/workflows/coverage.yml"


def test_coverage_workflow_targets_imported_package_and_rejects_empty_data() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "--source=format_bench -m pytest" in workflow
    assert "--source=src" not in workflow
    assert "coverage report --fail-under=1" in workflow
    assert workflow.index("coverage report --fail-under=1") < workflow.index(
        "coverage xml"
    )
