"""Idempotent REST synchronization for the strict-audit tracker."""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Literal, cast

from audit_tracker import AuditError, AuditItem, validate_ui_readback
from github_labels import LabelSpec, plan_labels

MARKER = "data-format-lab-audit:v1"
MARKER_RE = re.compile(r"<!-- data-format-lab-audit:v1 id=([^ ]+) -->")

SyncState = Literal["PLANNED", "APPLIED", "VERIFIED"]
IssueState = Literal["open", "closed"]

# LLM contract: audit synchronization advances only
# PLANNED -> APPLIED -> VERIFIED. A failed or uncertain mutation does not
# advance state; the next attempt must read live state and re-plan.
SYNC_TRANSITIONS: dict[SyncState, frozenset[SyncState]] = {
    "PLANNED": frozenset({"APPLIED"}),
    "APPLIED": frozenset({"VERIFIED"}),
    "VERIFIED": frozenset(),
}


def transition_sync(current: SyncState, target: SyncState) -> SyncState:
    if current == target:
        return current
    if target not in SYNC_TRANSITIONS[current]:
        raise AuditError(f"illegal audit sync transition: {current} -> {target}")
    return target


@dataclass(frozen=True)
class IssueSpec:
    key: str
    title: str
    body: str
    labels: tuple[str, ...]
    milestone: str | None


@dataclass(frozen=True)
class LiveIssue:
    number: int
    title: str
    body: str
    labels: frozenset[str]
    milestone: str | None
    state: IssueState = "open"


@dataclass(frozen=True)
class LiveState:
    labels: dict[str, dict[str, object]]
    milestones: dict[str, dict[str, object]]
    issues: dict[str, LiveIssue]
    existing: LiveIssue


@dataclass(frozen=True)
class Mutation:
    method: Literal["POST", "PATCH"]
    path: str
    key: str
    payload: dict[str, object]


class GitHubRest:
    def _call(self, args: list[str], payload: dict[str, object] | None, attempts: int) -> object:
        for attempt in range(attempts):
            try:
                result = subprocess.run(
                    ["gh", "api", *args], input=json.dumps(payload) if payload else None,
                    capture_output=True, text=True, check=False,
                )
            except OSError as error:
                raise AuditError(f"cannot execute gh api: {error}") from error
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout) if result.stdout.strip() else None
                except json.JSONDecodeError as error:
                    raise AuditError("gh api returned invalid JSON") from error
            if attempt + 1 == attempts:
                raise AuditError(f"gh api failed: {result.stderr.strip()}")
            time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def get(self, path: str) -> object:
        return self._call([path], None, 3)

    def pages(self, path: str) -> object:
        return self._call(["--paginate", "--slurp", path], None, 3)

    def mutate(self, mutation: Mutation) -> object:
        return self._call(
            ["--method", mutation.method, mutation.path, "--input", "-"],
            mutation.payload, 1,
        )


def _obj(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AuditError(f"{context} must be an object")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise AuditError(f"{context} must be an object")
    return {cast(str, key): item for key, item in raw.items()}


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise AuditError(f"{context} must be a list")
    return cast(list[object], value)


def _text(data: dict[str, object], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise AuditError(f"{context}.{key} must be a string")
    return value


def _integer(data: dict[str, object], key: str, context: str) -> int:
    value = data.get(key)
    if type(value) is not int:
        raise AuditError(f"{context}.{key} must be an integer")
    return value


def _issue_state(data: dict[str, object]) -> IssueState:
    state = _text(data, "state", "issue")
    if state not in {"open", "closed"}:
        raise AuditError("issue.state must be open or closed")
    return cast(IssueState, state)


def _flatten_pages(value: object, context: str) -> list[dict[str, object]]:
    return [
        _obj(item, context)
        for page in _list(value, f"{context}.pages")
        for item in _list(page, f"{context}.page")
    ]


object_map, object_list, object_text, flatten_pages = _obj, _list, _text, _flatten_pages


def desired_issues(registry: dict[str, object], items: list[AuditItem]) -> tuple[IssueSpec, ...]:
    github = _obj(registry["github"], "github")
    audit_label = cast(str, github["audit_label"])
    specs = [IssueSpec(
        "DFL-AUDIT-ROOT", "[Audit 2026-07-19] Strict audit closure roadmap",
        "Tracks the 174-criterion strict audit: 85 actionable findings across 15 workstreams.\n\n"
        "Source: `docs/audits/2026-07-19/audit.json`.\n\n"
        "Project views and personal saved views require final GitHub UI setup.\n\n"
        f"<!-- {MARKER} id=DFL-AUDIT-ROOT -->",
        (audit_label, "ready-for-agent"), None,
    )]
    for raw in _list(registry["workstreams"], "workstreams"):
        workstream = _obj(raw, "workstream")
        key = _text(workstream, "key", "workstream")
        title = _text(workstream, "title", "workstream")
        blocked = ", ".join(cast(list[str], workstream["blocked_by"])) or "none"
        marker = f"DFL-AUDIT-WS-{key.upper()}"
        specs.append(IssueSpec(
            marker, f"[Audit] {title}",
            f"Closes the `{key}` workstream from the strict audit.\n\nBlocked by: {blocked}.\n\n"
            f"<!-- {MARKER} id={marker} -->",
            (audit_label, "ready-for-agent"),
            _text(workstream, "milestone", "workstream"),
        ))
    for item in items:
        if item.disposition != "ISSUE":
            continue
        if item.priority is None:
            raise AuditError(f"{item.id}: actionable priority is missing")
        labels = {audit_label, f"priority:{item.priority.lower()}", item.readiness_label, *item.labels}
        body = (
            f"## Finding\n\n**Original score:** {item.score}/10  \n**Owner:** {item.owner}  \n"
            f"**Priority:** {item.priority}  \n**Workstream:** `{item.workstream}`\n\n"
            f"## Evidence\n\n{item.evidence}\n\n## Acceptance\n\n"
            "Resolve the finding with reproducible evidence, or record an explicit accepted-risk decision.\n\n"
            f"Dependencies: {', '.join(item.dependencies) or 'none'}.\n\n"
            f"<!-- {MARKER} id={item.id} -->"
        )
        specs.append(IssueSpec(
            item.id, f"[{item.id}] {item.criterion}", body,
            tuple(sorted(labels)), item.milestone,
        ))
    if len(specs) != 101 or len({spec.key for spec in specs}) != 101:
        raise AuditError("expected 101 unique audit issue specifications")
    return tuple(specs)


def _live_issue(raw: dict[str, object]) -> LiveIssue:
    milestone = raw.get("milestone")
    labels = _list(raw.get("labels"), "issue.labels")
    return LiveIssue(
        _integer(raw, "number", "issue"),
        _text(raw, "title", "issue"),
        "" if raw.get("body") is None else _text(raw, "body", "issue"),
        frozenset(_text(_obj(label, "label"), "name", "label") for label in labels),
        None if milestone is None else _text(_obj(milestone, "milestone"), "title", "milestone"),
        _issue_state(raw),
    )


def read_live(client: GitHubRest, repository: str) -> LiveState:
    pages = _list(client.pages(f"repos/{repository}/issues?state=all&per_page=100"), "pages")
    raw_issues = [
        _obj(issue, "issue") for page in pages for issue in _list(page, "page")
        if "pull_request" not in _obj(issue, "issue")
    ]
    marked: dict[str, LiveIssue] = {}
    existing: LiveIssue | None = None
    for raw in raw_issues:
        issue = _live_issue(raw)
        if issue.number == 236:
            existing = issue
        match = MARKER_RE.search(issue.body)
        if match:
            if match.group(1) in marked:
                raise AuditError(f"duplicate audit marker {match.group(1)}")
            marked[match.group(1)] = issue
    if existing is None:
        raise AuditError("existing issue #236 is missing")
    label_rows = _flatten_pages(
        client.pages(f"repos/{repository}/labels?per_page=100"), "labels"
    )
    milestone_rows = _flatten_pages(
        client.pages(f"repos/{repository}/milestones?state=all&per_page=100"),
        "milestones",
    )
    labels = {_text(item, "name", "label"): item for item in label_rows}
    milestones = {_text(item, "title", "milestone"): item for item in milestone_rows}
    return LiveState(labels, milestones, marked, existing)


def _same_fields(
    desired: dict[str, object], current: dict[str, object], fields: tuple[str, ...]
) -> bool:
    return all(desired.get(field) == current.get(field) for field in fields)


def label_spec(value: object) -> LabelSpec:
    raw = _obj(value, "label")
    name, color = (_text(raw, key, "label") for key in ("name", "color"))
    description = raw.get("description")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise AuditError("label.description must be a string or null")
    if not name or re.fullmatch(r"[0-9A-Fa-f]{6}", color) is None or len(description) > 100:
        raise AuditError(f"invalid label specification: {name}")
    return LabelSpec(name, color.lower(), description)


def build_plan(registry: dict[str, object], items: list[AuditItem], live: LiveState) -> tuple[Mutation, ...]:
    github = _obj(registry["github"], "github")
    repository = cast(str, registry["repository"])
    foundation: list[Mutation] = []
    try:
        label_plan = plan_labels(
            repository,
            tuple(label_spec(raw) for raw in _list(github["labels"], "github.labels")),
            tuple(label_spec(label) for label in live.labels.values()),
        )
    except ValueError as error:
        raise AuditError(str(error)) from error
    foundation.extend(
        Mutation(item.method, item.path, f"label:{item.key}", item.payload)
        for item in label_plan
    )
    for raw in _list(github["milestones"], "github.milestones"):
        milestone = _obj(raw, "milestone")
        title = _text(milestone, "title", "milestone")
        current = live.milestones.get(title)
        if current is None:
            foundation.append(Mutation("POST", f"repos/{repository}/milestones", f"milestone:{title}", milestone))
        elif not _same_fields(milestone, current, ("title", "description", "due_on")):
            milestone_update = {**milestone, "due_on": milestone.get("due_on")}
            foundation.append(Mutation(
                "PATCH",
                f"repos/{repository}/milestones/{_integer(current, 'number', 'milestone')}",
                f"milestone:{title}",
                milestone_update,
            ))
    if foundation:
        return tuple(foundation)
    mutations: list[Mutation] = []
    specs = desired_issues(registry, items)
    managed_labels = frozenset(label for spec in specs for label in spec.labels)
    for spec in specs:
        milestone = live.milestones.get(spec.milestone or "")
        payload: dict[str, object] = {
            "title": spec.title, "body": spec.body, "labels": list(spec.labels),
            "milestone": (
                None if milestone is None else _integer(milestone, "number", "milestone")
            ),
        }
        current = live.issues.get(spec.key)
        if current is None:
            mutations.append(Mutation("POST", f"repos/{repository}/issues", spec.key, payload))
            continue
        # Issue closure is human-owned audit progress. Content synchronization must
        # not reopen a completed finding or treat closure as configuration drift.
        expected_labels = (current.labels - managed_labels) | frozenset(spec.labels)
        if (
            current.title != spec.title
            or current.body != spec.body
            or current.labels != expected_labels
            or current.milestone != spec.milestone
        ):
            payload["labels"] = sorted(expected_labels)
            mutations.append(Mutation("PATCH", f"repos/{repository}/issues/{current.number}", spec.key, payload))
    required = {cast(str, github["audit_label"]), "priority:p1", "bug", "ready-for-agent"}
    existing_plan = _obj(_list(github["existing_issues"], "existing_issues")[0], "existing")
    existing_labels = (live.existing.labels - managed_labels) | required
    if live.existing.labels != existing_labels or live.existing.milestone != existing_plan["milestone"]:
        milestone_title = _text(existing_plan, "milestone", "existing issue")
        milestone = live.milestones[milestone_title]
        mutations.append(Mutation(
            "PATCH", f"repos/{repository}/issues/236", "existing:236",
            {
                "labels": sorted(existing_labels),
                "milestone": _integer(milestone, "number", "milestone"),
            },
        ))
    return tuple(mutations)


def apply(
    client: GitHubRest,
    registry: dict[str, object],
    items: list[AuditItem],
    state: SyncState,
) -> SyncState:
    repository = cast(str, registry["repository"])
    for _phase in range(3):
        plan = build_plan(registry, items, read_live(client, repository))
        if not plan:
            return state if state == "VERIFIED" else transition_sync(state, "APPLIED")
        if state == "VERIFIED":
            raise AuditError("verified audit synchronization has drifted")
        for mutation in plan:
            try:
                client.mutate(mutation)
            except AuditError as error:
                remaining = build_plan(registry, items, read_live(client, repository))
                if any(item.key == mutation.key for item in remaining):
                    raise AuditError(f"mutation outcome unknown for {mutation.key}") from error
            time.sleep(0.15)
    raise AuditError("audit REST synchronization did not converge")


def verify(
    registry: dict[str, object],
    items: list[AuditItem],
    live: LiveState,
    state: SyncState,
) -> SyncState:
    pending = build_plan(registry, items, live)
    if pending or len(live.issues) != 101:
        raise AuditError(f"audit REST synchronization incomplete: {len(pending)} pending")
    github = _obj(registry["github"], "github")
    project = _obj(github["project"], "github.project")
    if project.get("views_verified") is not True or github.get("saved_views_verified") is not True:
        raise AuditError("GitHub project and saved views are not independently verified")
    validate_ui_readback(registry)
    return transition_sync(state, "VERIFIED")


def synchronized_registry(
    registry: dict[str, object],
    items: list[AuditItem],
    live: LiveState,
    state: SyncState,
) -> dict[str, object]:
    updated = _obj(json.loads(json.dumps(registry)), "registry")
    github = _obj(updated["github"], "github")
    github["sync_state"] = state
    updated["github"] = github
    raw_items = _list(updated["items"], "items")
    actionable = {item.id for item in items if item.disposition == "ISSUE"}
    for index, raw in enumerate(raw_items):
        item = _obj(raw, "item")
        item_id = _text(item, "id", "item")
        if item_id in actionable:
            issue = live.issues.get(item_id)
            if issue is None:
                raise AuditError(f"missing live issue for {item_id}")
            item["issue_number"] = issue.number
        raw_items[index] = item
    updated["items"] = raw_items
    return updated
