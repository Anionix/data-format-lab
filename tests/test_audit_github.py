import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import NotRequired, TypedDict, cast

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tools"))


class _ProjectFieldFixture(TypedDict):
    name: str
    type: str
    options: NotRequired[list[str]]


class _ProjectFixture(TypedDict):
    title: str
    description: str
    url: str
    views_verified: bool
    fields: list[_ProjectFieldFixture]


class _GitHubFixture(TypedDict):
    sync_state: str
    project: _ProjectFixture
    saved_views_verified: bool
    ui_readback: NotRequired[dict[str, object]]
    labels: list[dict[str, object]]
    milestones: list[dict[str, object]]


class _RegistryFixture(TypedDict):
    repository: str
    github: _GitHubFixture
    items: list[dict[str, object]]


def _module(name: str) -> ModuleType:
    path = ROOT / f"tools/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _registry() -> _RegistryFixture:
    raw = json.loads((ROOT / "docs/audits/2026-07-19/audit.json").read_text())
    return cast(_RegistryFixture, raw)


def test_desired_issue_contract_and_foundation_plan() -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    registry = _registry()
    registry["github"]["sync_state"] = "APPLIED"
    registry["github"]["project"]["views_verified"] = False
    registry["github"]["saved_views_verified"] = False
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
    assert github.label_spec({"name": "live", "color": "ABCDEF", "description": None}).description == ""


def test_issue_plan_converges_to_no_op() -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    registry = _registry()
    registry["github"]["sync_state"] = "APPLIED"
    registry["github"]["project"]["views_verified"] = False
    registry["github"]["saved_views_verified"] = False
    items = tracker.validate_registry(registry)
    specs = github.desired_issues(registry, items)
    config = registry["github"]
    labels = {cast(str, item["name"]): item for item in config["labels"]}
    milestones = {
        cast(str, item["title"]): {**item, "number": number}
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
    ui_readback = github_config.pop("ui_readback")
    with pytest.raises(tracker.AuditError, match="ui_readback"):
        github.verify(registry, items, live, "APPLIED")
    github_config["ui_readback"] = ui_readback
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


def test_project_contract_checks_identity_items_and_field_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    project = _module("audit_project")
    registry = _registry()
    registry["github"]["sync_state"] = "APPLIED"
    registry["github"]["project"]["views_verified"] = False
    registry["github"]["saved_views_verified"] = False
    items = tracker.validate_registry(registry)
    specs = github.desired_issues(registry, items)
    live_issues = {
        spec.key: github.LiveIssue(
            number, spec.title, spec.body, frozenset(spec.labels), spec.milestone
        )
        for number, spec in enumerate(specs, start=238)
    }
    live = github.LiveState({}, {}, live_issues, github.LiveIssue(236, "", "", frozenset(), None))
    configured = registry["github"]["project"]["fields"]
    fields = [
        {
            "name": field["name"],
            **(
                {"options": [{"name": option} for option in field["options"]]}
                if "options" in field
                else {}
            ),
        }
        for field in configured
    ]
    graph_fields = [
        {
            "name": field["name"],
            "__typename": (
                "ProjectV2SingleSelectField"
                if field["type"] == "SINGLE_SELECT"
                else "ProjectV2Field"
            ),
            **({"dataType": field["type"]} if field["type"] != "SINGLE_SELECT" else {}),
        }
        for field in configured
    ]
    project_items = [
        {
            "audit ID": spec.key,
            "content": {
                "type": "Issue", "repository": registry["repository"],
                "number": live_issues[spec.key].number,
            },
        }
        for spec in specs
    ] + [{
        "audit ID": "EXISTING-236",
        "content": {"type": "Issue", "repository": registry["repository"], "number": 236},
    }]

    def fake_gh(args: list[str]) -> object:
        if args[:2] == ["project", "list"]:
            return {"projects": [{"title": registry["github"]["project"]["title"], "number": 15}]}
        if args[:2] == ["project", "view"]:
            config = registry["github"]["project"]
            return {
                "public": True, "title": config["title"],
                "shortDescription": config["description"], "url": config["url"],
            }
        if args[:2] == ["project", "field-list"]:
            return {"fields": fields, "totalCount": 19}
        if args[:2] == ["project", "item-list"]:
            return {"items": project_items}
        return {
            "data": {"user": {"projectV2": {
                "repositories": {"nodes": [{"nameWithOwner": registry["repository"]}]},
                "fields": {"nodes": graph_fields},
            }}}
        }

    monkeypatch.setattr(project, "_gh", fake_gh)
    evidence = project.read_project(registry, items, live)
    assert (evidence.number, evidence.item_count, evidence.field_count) == (15, 102, 19)

    project_items[0]["content"]["number"] = 999
    with pytest.raises(tracker.AuditError, match="item content differs"):
        project.read_project(registry, items, live)
    project_items[0]["content"]["number"] = live_issues[specs[0].key].number

    score = next(field for field in graph_fields if field["name"] == "Audit Score")
    score["dataType"] = "TEXT"
    with pytest.raises(tracker.AuditError, match="field type differs"):
        project.read_project(registry, items, live)

    score["dataType"] = "NUMBER"
    status = next(field for field in fields if field["name"] == "Status")
    status_options = cast(list[dict[str, str]], status["options"])
    status_options.append({"name": "Unexpected"})
    with pytest.raises(tracker.AuditError, match="field options differ"):
        project.read_project(registry, items, live)

    status_options.pop()
    missing = live_issues.pop(specs[-1].key)
    live_issues["DFL-AUDIT-UNEXPECTED"] = missing
    with pytest.raises(tracker.AuditError, match="marker IDs differ"):
        project.read_project(registry, items, live)


def test_verify_cli_gates_transition_on_project_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    project = _module("audit_project")
    registry = _registry()
    items = tracker.validate_registry(registry)
    live = github.LiveState({}, {}, {}, None)
    calls: list[str] = []

    monkeypatch.setattr(tracker, "load_registry", lambda _path: registry)
    monkeypatch.setattr(tracker, "validate_registry", lambda _registry: items)
    monkeypatch.setattr(tracker, "render_report", lambda _registry, _items: "report\n")
    monkeypatch.setattr(tracker, "write_registry", lambda *_args: None)
    monkeypatch.setattr(Path, "read_text", lambda _path: "report\n")
    monkeypatch.setattr(github, "GitHubRest", lambda: object())
    monkeypatch.setattr(github, "read_live", lambda *_args: live)
    evidence = project.ProjectEvidence(15, "project", 102, 19, True)
    monkeypatch.setattr(
        project,
        "read_project",
        lambda *_args: calls.append("project") or evidence,
    )
    monkeypatch.setattr(
        project, "verify_hierarchy", lambda *_args: calls.append("hierarchy")
    )
    monkeypatch.setattr(
        github,
        "verify",
        lambda *_args: calls.append("transition") or "VERIFIED",
    )
    monkeypatch.setattr(
        github, "synchronized_registry", lambda *_args: registry
    )
    monkeypatch.setattr(
        project, "issue_map", lambda *_args: calls.append("map") or {}
    )
    monkeypatch.setattr(project, "write_issue_map", lambda *_args: None)

    assert tracker.main(["verify"]) == 0
    assert calls == ["project", "hierarchy", "map", "transition", "map"]


def test_hierarchy_and_issue_map_are_contract_driven(tmp_path: Path) -> None:
    tracker = _module("audit_tracker")
    github = _module("audit_github")
    project = _module("audit_project")
    registry = _registry()
    registry["github"]["sync_state"] = "APPLIED"
    registry["github"]["project"]["views_verified"] = False
    registry["github"]["saved_views_verified"] = False
    items = tracker.validate_registry(registry)
    specs = github.desired_issues(registry, items)
    live_issues = {
        spec.key: github.LiveIssue(
            number, spec.title, spec.body, frozenset(spec.labels), spec.milestone
        )
        for number, spec in enumerate(specs, start=238)
    }
    live = github.LiveState(
        {}, {}, live_issues, github.LiveIssue(236, "", "", frozenset(), None)
    )
    children, dependencies = project.hierarchy_contract(registry, items, live)
    blocking = {issue: set() for issue in dependencies}
    for issue, blockers in dependencies.items():
        for blocker in blockers:
            blocking[blocker].add(issue)

    class FakeRest:
        def get(self, path: str) -> list[dict[str, object]]:
            number = int(path.split("/issues/", 1)[1].split("/", 1)[0])
            if "/dependencies/blocked_by" in path:
                expected = dependencies[number]
            elif "/dependencies/blocking" in path:
                expected = blocking[number]
            else:
                expected = children[number]
            return [
                {
                    "number": issue_number,
                    "repository_url": "https://api.github.com/repos/Anionix/data-format-lab",
                }
                for issue_number in sorted(expected)
            ]

    project.verify_hierarchy(registry, items, live, FakeRest())
    assert len(children) == 102
    assert sum(len(value) for value in children.values()) == 101
    assert len(dependencies) == len(blocking) == 102

    class WrongRepositoryRest(FakeRest):
        def get(self, path: str) -> list[dict[str, object]]:
            rows = super().get(path)
            if rows:
                rows[0]["repository_url"] = "https://api.github.com/repos/Anionix/other"
            return rows

    with pytest.raises(tracker.AuditError, match="repository differs"):
        project.verify_hierarchy(registry, items, live, WrongRepositoryRest())

    evidence = project.ProjectEvidence(15, "project", 102, 19, True)
    mapping = project.issue_map(registry, items, live, evidence)
    output = tmp_path / "issue-map.json"
    project.write_issue_map(output, mapping)
    first = output.read_bytes()
    project.write_issue_map(output, mapping)

    assert output.read_bytes() == first
    assert len(mapping["issues"]) == 101
    assert mapping["issues"][0]["repository_path"].startswith(
        "/Anionix/data-format-lab/issues/"
    )
    assert len(mapping["pending_ui"]["project_views"]) == 6

    registry["github"]["project"]["views_verified"] = True
    registry["github"]["saved_views_verified"] = True
    assert project.issue_map(registry, items, live, evidence)["pending_ui"] == {
        "project_views": [],
        "saved_issue_views": [],
    }
