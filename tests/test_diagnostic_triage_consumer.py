import json
import shutil
import subprocess
import tomllib
from pathlib import Path


ROOT = Path(__file__).parents[1]
PIN = "d036a33bfc5a49c05f54200df9be8f55e2987cd6"
BINARY = "diagnostic-triage"


def _yaml_block(document: str, header: str) -> str:
    lines = document.splitlines()
    start = lines.index(header)
    indentation = len(header) - len(header.lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= indentation:
            end = index
            break
    return "\n".join(lines[start:end])


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which(BINARY)
    assert executable is not None, "the pinned Nix shell must expose diagnostic-triage"
    return subprocess.run(
        [executable, "--repository", str(ROOT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def _repository_state() -> bytes:
    return subprocess.run(
        ["git", "status", "--porcelain=v2", "-z", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=10,
    ).stdout


def test_config_matches_the_immutable_nix_input() -> None:
    config = tomllib.loads((ROOT / "diagnostic-triage.toml").read_text())
    lock = json.loads((ROOT / "flake.lock").read_text())
    input_name = lock["nodes"]["root"]["inputs"]["diagnostic-triage"]
    locked = lock["nodes"][input_name]["locked"]

    assert locked["rev"] == PIN == config["engine"]["source_revision"]
    assert config["engine"]["version"] == "0.1.0-alpha.1"
    assert config["repository"] == {"workspace": ".", "targets": ["."]}
    assert config["providers"] == [
        {
            "adapter_id": "ruff",
            "adapter_version": "0.1.0-alpha.1",
            "tool_name": "ruff",
            "tool_version": "0.15.20",
            "program": "diagnostic-triage-provider-python",
            "required": True,
            "required_capabilities": ["diagnostic.check/v1"],
        }
    ]
    assert config["output"] == {"format": "json"}


def test_check_is_read_only_and_emits_a_verdict_backed_report() -> None:
    before = _repository_state()
    result = _run("check")
    after = _repository_state()

    assert after == before
    assert result.returncode in {0, 1}, result.stderr
    report = json.loads(result.stdout)
    assert report["schema_version"] == "diagnostic-triage.session-report/v1"
    assert report["engine"]["source_revision"] == PIN
    assert (result.returncode, report["verdict"]) in {
        (0, "PASS"),
        (1, "POLICY_FAIL"),
    }


def test_invalid_config_and_missing_provider_are_operational_failures() -> None:
    for config in (
        "tests/fixtures/diagnostic-triage/malformed-config.toml",
        "tests/fixtures/diagnostic-triage/missing-provider.toml",
    ):
        result = _run("--config", config, "check")
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr


def test_github_actions_observer_is_offline_and_complete() -> None:
    result = _run(
        "observe",
        "--source",
        "github-actions",
        "--input",
        "tests/fixtures/diagnostic-triage/github-actions-success.json",
    )

    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[0]["kind"] == "manifest"
    assert events[-1]["kind"] == "completion"
    assert events[-1]["status"] == "COMPLETE"


def test_observation_outputs_do_not_pollute_repository_identity() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "diagnostic-triage-observe.yml"
    ).read_text()

    evidence_names = (
        "diagnostic-triage-report.json",
        "diagnostic-triage-observer.jsonl",
        "github-actions-run.json",
    )
    evidence_lines = [
        line
        for line in workflow.splitlines()
        if any(name in line for name in evidence_names)
    ]

    assert evidence_lines
    assert all(
        "RUNNER_TEMP" in line or "runner.temp" in line for line in evidence_lines
    )


def test_completed_ci_observation_uses_trusted_code_and_explicit_input() -> None:
    workflow = (
        ROOT / ".github" / "workflows" / "diagnostic-triage-observe.yml"
    ).read_text()
    workflow_header = workflow.split("jobs:", maxsplit=1)[0]
    concurrency = _yaml_block(workflow, "concurrency:")
    diagnostics = _yaml_block(workflow, "  diagnostics:")
    completed_run = _yaml_block(workflow, "  completed-run:")

    assert "workflow_run:" in workflow
    assert "workflows: [CI]" in workflow
    assert "types: [completed]" in workflow
    assert "permissions: {}" in workflow_header
    assert "actions: read" not in workflow_header

    assert (
        "group: diagnostic-triage-observe-"
        "${{ github.event.workflow_run.id || github.ref }}" in concurrency
    )
    assert "cancel-in-progress: true" in concurrency

    assert "if: github.event_name != 'workflow_run'" in diagnostics
    assert "actions: read" not in diagnostics
    assert "contents: read" in diagnostics
    assert "persist-credentials: false" in diagnostics
    assert "if: always() && github.event_name != 'pull_request'" in diagnostics

    assert "if: github.event_name == 'workflow_run'" in completed_run
    assert "actions: read" in completed_run
    assert "contents: read" in completed_run
    assert "ref: ${{ github.event.repository.default_branch }}" in completed_run
    assert "persist-credentials: false" in completed_run
    assert "head -c 16777217" in completed_run
    assert "16777216" in completed_run
    assert '.status == "completed" and .id == $observed_run_id' in completed_run
    assert "github.event.workflow_run.head_sha" not in workflow
    assert '"repos/$GITHUB_REPOSITORY/actions/runs/$OBSERVED_RUN_ID"' in completed_run
    assert '--input "$input"' in completed_run
