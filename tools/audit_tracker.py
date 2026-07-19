#!/usr/bin/env python3
"""Validate and render the immutable strict-audit registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/audits/2026-07-19/audit.json"
REPORT = ROOT / "docs/audits/2026-07-19/report.md"
SOURCE_DIGEST = "b701ddb9c10681c2ded72a5f65e4221321aa0df099a3042da4fd59e7c25994a0"
AUDITED_COMMIT = "52748f552bf2f5e7922725ea2e8f85bea291bce0"
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


@dataclass(frozen=True)
class AuditItem:
    id: str
    criterion: str
    score: int
    severity: str
    evidence: str
    disposition: str
    workstream: str
    priority: str | None
    owner: str
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
    if issue_number is not None and type(issue_number) is not int:
        raise AuditError("item.issue_number must be an integer or null")
    return AuditItem(
        id=_text(data, "id", "item"),
        criterion=_text(data, "criterion", "item"),
        score=score,
        severity=_text(data, "severity", "item"),
        evidence=_text(data, "evidence", "item"),
        disposition=_text(data, "disposition", "item"),
        workstream=_text(data, "workstream", "item"),
        priority=_optional_text(data, "priority", "item"),
        owner=_text(data, "owner", "item"),
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


def _band_counts(scores: list[int]) -> dict[str, int]:
    return {
        "1-3": sum(score <= 3 for score in scores),
        "4-5": sum(4 <= score <= 5 for score in scores),
        "6-7": sum(6 <= score <= 7 for score in scores),
        "8-10": sum(score >= 8 for score in scores),
    }


def _assert_acyclic(items: list[AuditItem]) -> None:
    graph = {item.id: item.dependencies for item in items}
    active: set[str] = set()
    complete: set[str] = set()

    def visit(node: str) -> None:
        if node in active:
            raise AuditError(f"dependency cycle at {node}")
        if node in complete:
            return
        active.add(node)
        for dependency in graph[node]:
            if dependency not in graph:
                raise AuditError(f"unknown dependency {dependency}")
            visit(dependency)
        active.remove(node)
        complete.add(node)

    for node in graph:
        visit(node)


def validate_registry(registry: dict[str, object]) -> list[AuditItem]:
    if set(registry) != TOP_LEVEL_FIELDS:
        raise AuditError("top-level fields differ from audit_registry/v1")
    if registry.get("schema_version") != "audit_registry/v1":
        raise AuditError("schema_version must be audit_registry/v1")
    for key in ("audit_date", "repository", "audited_commit", "method"):
        _text(registry, key, "registry")
    if registry.get("audited_commit") != AUDITED_COMMIT:
        raise AuditError("audited_commit differs from the immutable audit source")
    github = _mapping(registry.get("github"), "github")
    sync_state = _text(github, "sync_state", "github")
    if sync_state not in {"PLANNED", "APPLIED", "VERIFIED"}:
        raise AuditError("github.sync_state is invalid")
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
        expected = "ISSUE" if item.score <= 5 else "MONITOR" if item.score <= 7 else "REGRESSION_GUARD"
        expected_severity = (
            "HIGH" if item.score <= 3 else "MEDIUM" if item.score <= 5
            else "LOW" if item.score <= 7 else "INFORMATIONAL"
        )
        if item.disposition != expected or item.workstream not in keys:
            raise AuditError(f"{item.id}: invalid disposition or workstream")
        if item.severity != expected_severity:
            raise AuditError(f"{item.id}: severity does not match original_score")
        if item.owner not in {"Agent", "Human", "Mixed"}:
            raise AuditError(f"{item.id}: owner is invalid")
        if expected == "ISSUE" and None in (item.priority, item.milestone):
            raise AuditError(f"{item.id}: actionable fields are incomplete")
        if expected == "ISSUE" and item.priority not in {"P0", "P1", "P2", "P3"}:
            raise AuditError(f"{item.id}: priority is invalid")
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
    _assert_acyclic(items)
    return items


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
    parser.add_argument("command", choices=("validate",))
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.registry)
        report = render_report(registry, validate_registry(registry))
        if args.write_report:
            args.report.write_text(report)
        elif args.report.read_text() != report:
            raise AuditError("generated report is stale")
    except (AuditError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("audit registry valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
