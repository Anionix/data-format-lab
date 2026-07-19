import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).parents[1]


def _module(name: str) -> ModuleType:
    path = ROOT / f"tools/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _registry() -> dict[str, object]:
    return json.loads((ROOT / "docs/audits/2026-07-19/audit.json").read_text())


def test_desired_issue_contract_and_foundation_plan() -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    registry = _registry()
    items = tracker.validate_registry(registry)
    specs = github.desired_issues(registry, items)

    assert len(specs) == 101
    assert len({spec.key for spec in specs}) == 101
    assert all(f"id={spec.key} -->" in spec.body for spec in specs)
    assert all(spec.key != "EXISTING-236" for spec in specs)
    assert all(spec.milestone is not None for spec in specs[16:])

    existing = github.LiveIssue(236, "existing", "body", frozenset({"bug"}), None)
    plan = github.build_plan(registry, items, github.LiveState({}, {}, {}, existing))
    assert len(plan) == 10
    assert {mutation.key.split(":", 1)[0] for mutation in plan} == {"label", "milestone"}


def test_issue_plan_converges_to_no_op() -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    registry = _registry()
    items = tracker.validate_registry(registry)
    specs = github.desired_issues(registry, items)
    config = registry["github"]
    labels = {item["name"]: item for item in config["labels"]}
    milestones = {
        item["title"]: {**item, "number": number}
        for number, item in enumerate(config["milestones"], start=1)
    }
    existing_labels = frozenset({"audit:2026-07-19", "priority:p1", "bug", "ready-for-agent"})
    existing = github.LiveIssue(
        236, "existing", "body", existing_labels, "Audit M1 - Evidence Integrity"
    )
    live_issues = {
        spec.key: github.LiveIssue(
            number, spec.title, spec.body, frozenset(spec.labels), spec.milestone
        )
        for number, spec in enumerate(specs, start=238)
    }
    live = github.LiveState(labels, milestones, live_issues, existing)

    assert github.build_plan(registry, items, live) == ()
    with pytest.raises(tracker.AuditError, match="not independently verified"):
        github.verify(registry, items, live, "APPLIED")
    github_config = registry["github"]
    github_config["project"]["views_verified"] = True
    github_config["saved_views_verified"] = True
    assert github.verify(registry, items, live, "APPLIED") == "VERIFIED"

    first_key = specs[16].key
    current = live_issues[first_key]
    live_issues[first_key] = github.LiveIssue(
        current.number,
        current.title,
        current.body,
        current.labels,
        current.milestone,
        "closed",
    )
    closed_live = github.LiveState(labels, milestones, live_issues, existing)
    assert github.build_plan(registry, items, closed_live) == ()

    current = live_issues[first_key]
    stale_priority = next(
        label
        for label in ("priority:p0", "priority:p1", "priority:p2", "priority:p3")
        if label not in current.labels
    )
    live_issues[first_key] = github.LiveIssue(
        current.number,
        current.title,
        "drifted body",
        current.labels | {"human-added", stale_priority},
        current.milestone,
    )
    issue_plan = github.build_plan(
        registry, items, github.LiveState(labels, milestones, live_issues, existing)
    )
    assert "human-added" in issue_plan[0].payload["labels"]
    assert stale_priority not in issue_plan[0].payload["labels"]
    assert "state" not in issue_plan[0].payload

    stale_labels = {name: dict(value) for name, value in labels.items()}
    stale_labels["priority:p0"]["color"] = "ffffff"
    metadata_plan = github.build_plan(
        registry, items, github.LiveState(stale_labels, milestones, {}, existing)
    )
    assert metadata_plan[0].key == "label:priority:p0"
    assert metadata_plan[0].method == "PATCH"
    assert metadata_plan[0].payload["new_name"] == "priority:p0"
    assert "name" not in metadata_plan[0].payload

    stale_milestones = {name: dict(value) for name, value in milestones.items()}
    stale_milestones["Audit M1 - Evidence Integrity"]["due_on"] = "2026-08-01T00:00:00Z"
    milestone_plan = github.build_plan(
        registry, items, github.LiveState(labels, stale_milestones, {}, existing)
    )
    assert milestone_plan[0].key == "milestone:Audit M1 - Evidence Integrity"
    assert milestone_plan[0].payload["due_on"] is None


def test_apply_mapping_preserves_live_issue_identity() -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    registry = _registry()
    items = tracker.validate_registry(registry)
    specs = github.desired_issues(registry, items)
    live_issues = {
        spec.key: github.LiveIssue(
            number, spec.title, spec.body, frozenset(spec.labels), spec.milestone
        )
        for number, spec in enumerate(specs, start=238)
    }
    existing = github.LiveIssue(236, "existing", "body", frozenset(), None)
    applied = github.synchronized_registry(
        registry, items, github.LiveState({}, {}, live_issues, existing), "APPLIED"
    )

    assert applied["github"]["sync_state"] == "APPLIED"
    numbers = [
        item["issue_number"]
        for item in applied["items"]
        if item["disposition"] == "ISSUE"
    ]
    assert len(numbers) == len(set(numbers)) == 85

    verified = github.synchronized_registry(
        applied, items, github.LiveState({}, {}, live_issues, existing), "VERIFIED"
    )
    assert verified["github"]["sync_state"] == "VERIFIED"


def test_sync_lifecycle_rejects_skips_and_reverse_transitions() -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")

    assert github.transition_sync("PLANNED", "APPLIED") == "APPLIED"
    assert github.transition_sync("APPLIED", "VERIFIED") == "VERIFIED"
    assert github.transition_sync("VERIFIED", "VERIFIED") == "VERIFIED"
    for current, target in (("PLANNED", "VERIFIED"), ("APPLIED", "PLANNED")):
        try:
            github.transition_sync(current, target)
        except tracker.AuditError:
            pass
        else:
            raise AssertionError(f"accepted illegal transition: {current} -> {target}")
