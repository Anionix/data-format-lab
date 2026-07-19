#!/usr/bin/env python3
"""Validate and render the immutable strict-audit registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

if __name__ == "__main__":
    sys.modules.setdefault("audit_tracker", sys.modules[__name__])

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/audits/2026-07-19/audit.json"
REPORT = ROOT / "docs/audits/2026-07-19/report.md"
SOURCE_DIGEST = "b701ddb9c10681c2ded72a5f65e4221321aa0df099a3042da4fd59e7c25994a0"
GITHUB_PLAN_DIGEST = "c5c40d0c81a021e4d242b30c7fe5d7dd70cd86069bd07c80499b3b863f922ac3"
TRIAGE_DIGEST = "a2837f8456b0511d2b5620be00cb6d26b4f3ff4fde471525c3292a0ff810cd3a"
AUDITED_COMMIT = "52748f552bf2f5e7922725ea2e8f85bea291bce0"
AUDIT_DATE = "2026-07-19"
REPOSITORY = "Anionix/data-format-lab"
AUDIT_METHOD = (
    "Six-role strict audit consolidated from 156 raw judgments into "
    "174 non-duplicate criteria."
)
P0_IDS = {139, 148, 151, 154, 155, 161, 162}
P1_IDS = {17, 53, 54, 95, 102, *range(163, 170), *range(171, 175)}
HUMAN_IDS = {145, *range(152, 156), 161, 162}
MIXED_IDS = {139, 144, *range(148, 152), 157, 159}
SCORE_BANDS = {"1-3": 43, "4-5": 42, "6-7": 36, "8-10": 53}
TOP_LEVEL_FIELDS = {
    "schema_version", "audit_date", "repository", "audited_commit", "source_digest",
    "method", "score_bands", "workstreams", "github", "items",
}
ITEM_FIELDS = {
    "id", "criterion", "original_score", "severity", "evidence", "disposition",
    "workstream", "priority", "owner", "milestone", "dependencies", "labels",
    "readiness_label", "issue_number",
}

# LLM contract: benchmark evidence remains
# DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.


class AuditError(RuntimeError):
    """The registry violates its public contract."""


Severity = Literal["HIGH", "MEDIUM", "LOW", "INFORMATIONAL"]
Disposition = Literal["ISSUE", "MONITOR", "REGRESSION_GUARD"]
Priority = Literal["P0", "P1", "P2", "P3"]
Owner = Literal["Agent", "Human", "Mixed"]


@dataclass(frozen=True)
class AuditItem:
    id: str
    criterion: str
    score: int
    severity: Severity
    evidence: str
    disposition: Disposition
    workstream: str
    priority: Priority | None
    owner: Owner
    milestone: str | None
    dependencies: tuple[str, ...]
    labels: tuple[str, ...]
    readiness_label: str
    issue_number: int | None


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AuditError(f"{context} must be an object with string keys")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise AuditError(f"{context} must be an object with string keys")
    return {str(key): item for key, item in raw.items()}


def _sequence(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise AuditError(f"{context} must be a list")
    return cast(list[object], value)


def _text(data: dict[str, object], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise AuditError(f"{context}.{key} must be a non-empty string")
    return value


def _optional_text(data: dict[str, object], key: str, context: str) -> str | None:
    value = data.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise AuditError(f"{context}.{key} must be a non-empty string or null")
    return value


def _records(
    value: object, context: str, fields: tuple[str, ...]
) -> list[dict[str, str]]:
    rows = [_mapping(raw, context) for raw in _sequence(value, context)]
    if any(set(row) != set(fields) for row in rows):
        raise AuditError(f"{context} fields differ")
    return [{field: _text(row, field, context) for field in fields} for row in rows]


def _item(value: object) -> AuditItem:
    data = _mapping(value, "item")
    if set(data) != ITEM_FIELDS:
        raise AuditError("item fields differ from audit_registry/v1")
    score = data.get("original_score")
    if type(score) is not int or not 1 <= score <= 10:
        raise AuditError("item.original_score must be an integer from 1 to 10")
    dependencies = _sequence(data.get("dependencies"), "item.dependencies")
    labels = _sequence(data.get("labels"), "item.labels")
    if not all(isinstance(dependency, str) for dependency in dependencies):
        raise AuditError("item.dependencies must contain strings")
    if not all(isinstance(label, str) and label for label in labels):
        raise AuditError("item.labels must contain non-empty strings")
    issue_number = data.get("issue_number")
    if issue_number is not None and (type(issue_number) is not int or issue_number <= 0):
        raise AuditError("item.issue_number must be a positive integer or null")
    severity = _text(data, "severity", "item")
    disposition = _text(data, "disposition", "item")
    priority = _optional_text(data, "priority", "item")
    owner = _text(data, "owner", "item")
    if severity not in {"HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}:
        raise AuditError("item.severity is invalid")
    if disposition not in {"ISSUE", "MONITOR", "REGRESSION_GUARD"}:
        raise AuditError("item.disposition is invalid")
    if priority is not None and priority not in {"P0", "P1", "P2", "P3"}:
        raise AuditError("item.priority is invalid")
    if owner not in {"Agent", "Human", "Mixed"}:
        raise AuditError("item.owner is invalid")
    return AuditItem(
        id=_text(data, "id", "item"),
        criterion=_text(data, "criterion", "item"),
        score=score,
        severity=cast(Severity, severity),
        evidence=_text(data, "evidence", "item"),
        disposition=cast(Disposition, disposition),
        workstream=_text(data, "workstream", "item"),
        priority=cast(Priority | None, priority),
        owner=cast(Owner, owner),
        milestone=_optional_text(data, "milestone", "item"),
        dependencies=tuple(str(dependency) for dependency in dependencies),
        labels=tuple(str(label) for label in labels),
        readiness_label=_text(data, "readiness_label", "item"),
        issue_number=issue_number,
    )


def load_registry(path: Path = REGISTRY) -> dict[str, object]:
    try:
        return _mapping(json.loads(path.read_text()), "registry")
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read registry: {error}") from error


def write_registry(path: Path, registry: dict[str, object]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def _band_counts(scores: list[int]) -> dict[str, int]:
    return {
        "1-3": sum(score <= 3 for score in scores),
        "4-5": sum(4 <= score <= 5 for score in scores),
        "6-7": sum(6 <= score <= 7 for score in scores),
        "8-10": sum(score >= 8 for score in scores),
    }


def _assert_graph_acyclic(graph: dict[str, tuple[str, ...]], context: str) -> None:
    active: set[str] = set()
    complete: set[str] = set()

    def visit(node: str) -> None:
        if node in active:
            raise AuditError(f"{context} dependency cycle at {node}")
        if node in complete:
            return
        if node not in graph:
            raise AuditError(f"unknown {context} dependency {node}")
        active.add(node)
        for dependency in graph[node]:
            visit(dependency)
        active.remove(node)
        complete.add(node)

    for node in graph:
        visit(node)


def validate_ui_readback(registry: dict[str, object]) -> None:
    github = _mapping(registry.get("github"), "github")
    reference = _mapping(github.get("ui_readback"), "github.ui_readback")
    if set(reference) != {"path", "sha256"}:
        raise AuditError("github.ui_readback fields differ from the evidence reference")
    relative_path = Path(_text(reference, "path", "github.ui_readback"))
    evidence_path = ROOT / relative_path
    root = ROOT.resolve()
    path_components = [
        ROOT.joinpath(*relative_path.parts[:index])
        for index in range(1, len(relative_path.parts) + 1)
    ]
    if (
        relative_path.is_absolute()
        or any(component.is_symlink() for component in path_components)
        or not evidence_path.resolve().is_relative_to(root)
    ):
        raise AuditError("github.ui_readback.path must be a non-symlink repository path")
    try:
        raw_evidence = evidence_path.read_bytes()
        evidence = _mapping(json.loads(raw_evidence), "ui readback evidence")
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read UI evidence: {error}") from error
    if hashlib.sha256(raw_evidence).hexdigest() != _text(
        reference, "sha256", "github.ui_readback"
    ):
        raise AuditError("UI evidence SHA-256 differs")
    if set(evidence) != {
        "schema_version", "method", "captured_at", "actor", "project",
        "saved_issue_views",
    } or evidence.get("schema_version") != "audit_ui_readback/v1":
        raise AuditError("UI evidence fields differ from audit_ui_readback/v1")
    if _text(evidence, "method", "UI evidence") != "authenticated_github_ui":
        raise AuditError("github.ui_readback.method is invalid")
    captured_at = _text(evidence, "captured_at", "UI evidence")
    try:
        datetime.strptime(captured_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise AuditError(
            "github.ui_readback.captured_at must be a UTC timestamp"
        ) from error
    if _text(evidence, "actor", "UI evidence") != _text(github, "project_owner", "github"):
        raise AuditError("github.ui_readback.actor differs from the Project owner")

    configured_project = _mapping(github.get("project"), "github.project")
    observed_project = _mapping(evidence.get("project"), "UI evidence.project")
    if set(observed_project) != {"url", "views"}:
        raise AuditError("UI evidence.project fields differ")
    if _text(observed_project, "url", "UI evidence.project") != _text(
        configured_project, "url", "github.project"
    ):
        raise AuditError("UI evidence Project URL differs")
    view_fields = ("name", "url", "filter")
    if _records(observed_project.get("views"), "UI evidence views", view_fields) != _records(
        configured_project.get("views"), "configured views", view_fields
    ):
        raise AuditError("UI evidence Project views differ")
    saved_fields = ("name", "url", "query")
    if _records(
        evidence.get("saved_issue_views"), "UI evidence saved views", saved_fields
    ) != _records(github.get("saved_views"), "configured saved views", saved_fields):
        raise AuditError("UI evidence saved views differ")


def validate_registry(registry: dict[str, object]) -> list[AuditItem]:
    if set(registry) != TOP_LEVEL_FIELDS:
        raise AuditError("top-level fields differ from audit_registry/v1")
    if registry.get("schema_version") != "audit_registry/v1":
        raise AuditError("schema_version must be audit_registry/v1")
    for key in ("audit_date", "repository", "audited_commit", "method"):
        _text(registry, key, "registry")
    if (
        registry.get("audit_date"), registry.get("repository"), registry.get("method")
    ) != (AUDIT_DATE, REPOSITORY, AUDIT_METHOD):
        raise AuditError("audit identity differs from the immutable audit source")
    if registry.get("audited_commit") != AUDITED_COMMIT:
        raise AuditError("audited_commit differs from the immutable audit source")
    github = _mapping(registry.get("github"), "github")
    sync_state = _text(github, "sync_state", "github")
    if sync_state not in {"PLANNED", "APPLIED", "VERIFIED"}:
        raise AuditError("github.sync_state is invalid")
    project = _mapping(github.get("project"), "github.project")
    if type(project.get("views_verified")) is not bool:
        raise AuditError("github.project.views_verified must be a boolean")
    if type(github.get("saved_views_verified")) is not bool:
        raise AuditError("github.saved_views_verified must be a boolean")
    canonical_github = dict(github)
    canonical_github.pop("ui_readback", None)
    canonical_project = dict(project)
    canonical_github["sync_state"] = "PLANNED"
    canonical_github["saved_views_verified"] = False
    canonical_project["views_verified"] = False
    canonical_github["project"] = canonical_project
    github_digest = hashlib.sha256(
        json.dumps(
            canonical_github, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if github_digest != GITHUB_PLAN_DIGEST:
        raise AuditError("GitHub plan differs from the canonical audit plan")
    items = [_item(value) for value in _sequence(registry.get("items"), "items")]
    if [item.id for item in items] != [f"DFL-AUDIT-{number:03d}" for number in range(1, 175)]:
        raise AuditError("audit IDs must be contiguous from 001 to 174")
    immutable = [[item.id, item.criterion, item.score, item.evidence] for item in items]
    digest = hashlib.sha256(
        json.dumps(immutable, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != SOURCE_DIGEST or registry.get("source_digest") != SOURCE_DIGEST:
        raise AuditError("immutable audit source digest differs")
    bands = _band_counts([item.score for item in items])
    if bands != SCORE_BANDS or registry.get("score_bands") != SCORE_BANDS:
        raise AuditError(f"score bands differ: {bands}")

    workstreams = _sequence(registry.get("workstreams"), "workstreams")
    workstream_graph: dict[str, tuple[str, ...]] = {}
    workstream_milestones: dict[str, str] = {}
    for value in workstreams:
        workstream = _mapping(value, "workstream")
        if set(workstream) != {"key", "title", "blocked_by", "milestone"}:
            raise AuditError("workstream fields differ from audit_registry/v1")
        key = _text(workstream, "key", "workstream")
        _text(workstream, "title", "workstream")
        workstream_milestones[key] = _text(workstream, "milestone", "workstream")
        blocked_by = _sequence(workstream.get("blocked_by"), "workstream.blocked_by")
        if not all(isinstance(blocker, str) for blocker in blocked_by):
            raise AuditError("workstream.blocked_by must contain strings")
        workstream_graph[key] = tuple(str(blocker) for blocker in blocked_by)
    keys = set(workstream_graph)
    if len(workstreams) != 15 or len(keys) != 15:
        raise AuditError("exactly 15 unique workstreams are required")
    _assert_graph_acyclic(workstream_graph, "workstream")
    for item in items:
        number = int(item.id.rsplit("-", 1)[1])
        expected = "ISSUE" if item.score <= 5 else "MONITOR" if item.score <= 7 else "REGRESSION_GUARD"
        expected_severity = (
            "HIGH" if item.score <= 3 else "MEDIUM" if item.score <= 5
            else "LOW" if item.score <= 7 else "INFORMATIONAL"
        )
        if item.disposition != expected or item.workstream not in keys:
            raise AuditError(f"{item.id}: invalid disposition or workstream")
        if item.severity != expected_severity:
            raise AuditError(f"{item.id}: severity does not match original_score")
        if expected == "ISSUE" and None in (item.priority, item.milestone):
            raise AuditError(f"{item.id}: actionable fields are incomplete")
        canonical_priority = (
            "P0" if number in P0_IDS else "P1" if number in P1_IDS
            else "P3" if item.score == 5 else "P2"
        )
        if expected == "ISSUE" and item.priority != canonical_priority:
            raise AuditError(f"{item.id}: priority differs from the audit plan")
        canonical_owner = "Human" if number in HUMAN_IDS else "Mixed" if number in MIXED_IDS else "Agent"
        if expected == "ISSUE" and item.owner != canonical_owner:
            raise AuditError(f"{item.id}: owner differs from the audit plan")
        if expected == "ISSUE" and item.milestone != workstream_milestones[item.workstream]:
            raise AuditError(f"{item.id}: milestone does not match workstream")
        expected_readiness = "ready-for-agent" if item.owner == "Agent" else "ready-for-human"
        if expected == "ISSUE" and item.readiness_label != expected_readiness:
            raise AuditError(f"{item.id}: canonical readiness label is missing")
        if expected == "ISSUE" and not item.labels:
            raise AuditError(f"{item.id}: at least one classification label is required")
        if expected == "ISSUE" and (sync_state == "PLANNED") != (item.issue_number is None):
            raise AuditError(f"{item.id}: issue_number does not match GitHub sync state")
        if expected != "ISSUE" and any(
            value is not None and value != ()
            for value in (item.priority, item.milestone, item.labels, item.issue_number)
        ):
            raise AuditError(f"{item.id}: non-actionable item has issue-only metadata")
    if sum(item.disposition == "ISSUE" for item in items) != 85:
        raise AuditError("exactly 85 actionable findings are required")
    synced_numbers = [item.issue_number for item in items if item.issue_number is not None]
    if sync_state != "PLANNED" and len(set(synced_numbers)) != 85:
        raise AuditError("synced issue numbers must be present and unique")
    if "ui_readback" in github:
        validate_ui_readback(registry)
    elif project["views_verified"] or github["saved_views_verified"]:
        raise AuditError("verified views require external UI readback evidence")
    if sync_state == "VERIFIED" and not (
        project["views_verified"] and github["saved_views_verified"]
    ):
        raise AuditError("VERIFIED sync requires verified project and saved views")
    _assert_graph_acyclic({item.id: item.dependencies for item in items}, "item")
    triage_keys = (
        "id", "severity", "disposition", "workstream", "priority", "owner",
        "milestone", "dependencies", "labels", "readiness_label",
    )
    triage = {
        "workstreams": workstreams,
        "items": [
            [_mapping(value, "item").get(key) for key in triage_keys]
            for value in _sequence(registry.get("items"), "items")
        ],
    }
    triage_digest = hashlib.sha256(
        json.dumps(
            triage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    if triage_digest != TRIAGE_DIGEST:
        raise AuditError("triage assignments differ from the canonical audit plan")
    return items


def render_report(registry: dict[str, object], items: list[AuditItem]) -> str:
    counts = Counter(item.disposition for item in items)
    lines = [
        "# Strict Audit Registry",
        "",
        f"Audit date: `{registry['audit_date']}`",
        f"Audited commit: `{registry['audited_commit']}`",
        "Generated from [`audit.json`](audit.json). Do not edit this report directly.",
        "",
        "## Summary",
        "",
        "| Disposition | Count |",
        "| --- | ---: |",
        *[f"| {name} | {counts[name]} |" for name in ("ISSUE", "MONITOR", "REGRESSION_GUARD")],
        "",
    ]
    for raw in _sequence(registry["workstreams"], "workstreams"):
        workstream = _mapping(raw, "workstream")
        key = _text(workstream, "key", "workstream")
        lines += [
            f"## {_text(workstream, 'title', 'workstream')}",
            "",
            "| ID | Criterion | Score | Disposition | Priority | Owner | Evidence |",
            "| --- | --- | ---: | --- | --- | --- | --- |",
        ]
        for item in (candidate for candidate in items if candidate.workstream == key):
            lines.append(
                f"| {item.id} | {item.criterion.replace('|', '\\|')} | {item.score} | "
                f"{item.disposition} | {item.priority or '-'} | {item.owner} | "
                f"{item.evidence.replace('|', '\\|').replace(chr(10), ' ')} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "plan", "apply", "verify"))
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.registry)
        items = validate_registry(registry)
        report = render_report(registry, items)
        if args.write_report:
            args.report.write_text(report)
        elif args.report.read_text() != report:
            raise AuditError("generated report is stale")
        if args.command != "validate":
            import audit_github

            client = audit_github.GitHubRest()
            live = audit_github.read_live(client, str(registry["repository"]))
            github_config = _mapping(registry["github"], "github")
            sync_state = cast(audit_github.SyncState, github_config["sync_state"])
            if args.command == "plan":
                plan = audit_github.build_plan(registry, items, live)
                print(
                    json.dumps(
                        [
                            {
                                "method": mutation.method,
                                "path": mutation.path,
                                "key": mutation.key,
                                "payload": mutation.payload,
                            }
                            for mutation in plan
                        ],
                        indent=2,
                    )
                )
            elif args.command == "apply":
                next_state = audit_github.apply(client, registry, items, sync_state)
                live = audit_github.read_live(client, str(registry["repository"]))
                updated = audit_github.synchronized_registry(
                    registry, items, live, next_state
                )
                validate_registry(updated)
                write_registry(args.registry, updated)
                print(f"next sync state: {next_state}")
            else:
                import audit_project

                audit_project.read_project(registry, items, live)
                next_state = audit_github.verify(registry, items, live, sync_state)
                updated = audit_github.synchronized_registry(
                    registry, items, live, next_state
                )
                validate_registry(updated)
                write_registry(args.registry, updated)
                print(
                    f"next sync state: "
                    f"{next_state}"
                )
    except (AuditError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"audit {args.command} complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
