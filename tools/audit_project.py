"""Read-only verification and publication for the strict-audit Project."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import cast

from audit_github import LiveState, desired_issues
from audit_tracker import AuditError, AuditItem

TRANSIENT_GH_ERRORS = (
    "http 429", "http 500", "http 502", "http 503", "http 504",
    "timeout", "temporarily unavailable", "connection reset",
)


@dataclass(frozen=True)
class ProjectEvidence:
    number: int
    url: str
    item_count: int
    field_count: int
    repository_linked: bool


# LLM contract: PLANNED -> APPLIED -> VERIFIED. This read-only Project
# contract can gate APPLIED evidence, but never advances synchronization state.


def _obj(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AuditError(f"{context} must be an object")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise AuditError(f"{context} must have string keys")
    return {cast(str, key): item for key, item in raw.items()}


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise AuditError(f"{context} must be a list")
    return cast(list[object], value)


def _strings(value: object, context: str) -> list[str]:
    values = _list(value, context)
    if not all(isinstance(item, str) for item in values):
        raise AuditError(f"{context} must contain strings")
    return [cast(str, item) for item in values]


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


def _gh(args: list[str]) -> object:
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["gh", *args], capture_output=True, text=True, check=False
            )
        except OSError as error:
            raise AuditError(f"cannot execute gh: {error}") from error
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as error:
                raise AuditError("gh returned invalid JSON") from error
        message = result.stderr.strip()
        transient = any(token in message.lower() for token in TRANSIENT_GH_ERRORS)
        if attempt == 2 or not transient:
            raise AuditError(f"gh read failed: {message}")
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _project_number(registry: dict[str, object]) -> int:
    github = _obj(registry.get("github"), "github")
    owner = _text(github, "project_owner", "github")
    config = _obj(github.get("project"), "github.project")
    result = _obj(
        _gh(["project", "list", "--owner", owner, "--limit", "100", "--format", "json"]),
        "project list",
    )
    matches = [
        _obj(raw, "project")
        for raw in _list(result.get("projects"), "projects")
        if _text(_obj(raw, "project"), "title", "project")
        == _text(config, "title", "github.project")
    ]
    if len(matches) != 1:
        raise AuditError("expected exactly one strict-audit Project")
    return _integer(matches[0], "number", "project")


def read_project(
    registry: dict[str, object], items: list[AuditItem], live: LiveState
) -> ProjectEvidence:
    github = _obj(registry.get("github"), "github")
    owner = _text(github, "project_owner", "github")
    config = _obj(github.get("project"), "github.project")
    number = _project_number(registry)
    view = _obj(
        _gh(["project", "view", str(number), "--owner", owner, "--format", "json"]),
        "project view",
    )
    if view.get("public") is not True or _text(view, "title", "project") != _text(
        config, "title", "github.project"
    ):
        raise AuditError("strict-audit Project identity or visibility differs")
    if _text(view, "shortDescription", "project") != _text(
        config, "description", "github.project"
    ):
        raise AuditError("strict-audit Project description differs")
    project_url = _text(view, "url", "project")
    if project_url != _text(config, "url", "github.project"):
        raise AuditError("strict-audit Project URL differs")

    field_result = _obj(
        _gh(["project", "field-list", str(number), "--owner", owner, "--format", "json"]),
        "project fields",
    )
    fields = {
        _text(field, "name", "field"): field
        for raw in _list(field_result.get("fields"), "fields")
        for field in [_obj(raw, "field")]
    }
    for raw in _list(config.get("fields"), "configured fields"):
        desired = _obj(raw, "configured field")
        name = _text(desired, "name", "configured field")
        current = fields.get(name)
        if current is None:
            raise AuditError(f"Project field is missing: {name}")
        if "options" in desired:
            options = [
                _text(_obj(option, "option"), "name", "option")
                for option in _list(current.get("options"), f"{name}.options")
            ]
            if options != _strings(desired.get("options"), f"{name}.configured options"):
                raise AuditError(f"Project field options differ: {name}")

    specs = desired_issues(registry, items)
    marker_ids = {spec.key for spec in specs}
    if set(live.issues) != marker_ids:
        raise AuditError("Project contract marker IDs differ")
    repository = _text(registry, "repository", "registry")
    expected_content = {key: live.issues[key].number for key in marker_ids}
    expected_content["EXISTING-236"] = 236
    item_result = _obj(
        _gh([
            "project", "item-list", str(number), "--owner", owner,
            "--limit", "1000", "--format", "json",
        ]),
        "project items",
    )
    project_items = [_obj(raw, "project item") for raw in _list(item_result.get("items"), "items")]
    observed_content: dict[str, int] = {}
    for item in project_items:
        audit_id = _text(item, "audit ID", "project item")
        content = _obj(item.get("content"), "project item.content")
        if (
            audit_id in observed_content
            or _text(content, "type", "project item.content") != "Issue"
            or _text(content, "repository", "project item.content") != repository
        ):
            raise AuditError("Project Audit ID item content differs")
        observed_content[audit_id] = _integer(content, "number", "project item.content")
    if observed_content != expected_content:
        raise AuditError("Project Audit ID item content differs")

    query = (
        "query { user(login:" + json.dumps(owner) + ") { projectV2(number:"
        + str(number)
        + ") { repositories(first:100) { nodes { nameWithOwner } } "
        + "fields(first:100) { nodes { __typename "
        + "... on ProjectV2Field { name dataType } "
        + "... on ProjectV2SingleSelectField { name } } } } } }"
    )
    graph = _obj(_gh(["api", "graphql", "-f", f"query={query}"]), "graphql")
    data = _obj(graph.get("data"), "graphql.data")
    user = _obj(data.get("user"), "graphql.user")
    project = _obj(user.get("projectV2"), "graphql.project")
    graph_fields = _obj(project.get("fields"), "graphql.fields")
    fields_by_name = {
        _text(field, "name", "graphql field"): field
        for raw in _list(graph_fields.get("nodes"), "graphql.fields.nodes")
        for field in [_obj(raw, "graphql field")]
        if isinstance(field.get("name"), str)
    }
    for raw in _list(config.get("fields"), "configured fields"):
        desired = _obj(raw, "configured field")
        name = _text(desired, "name", "configured field")
        expected_type = _text(desired, "type", "configured field")
        current = fields_by_name.get(name)
        if current is None:
            raise AuditError(f"Project GraphQL field is missing: {name}")
        typename = _text(current, "__typename", "graphql field")
        if expected_type == "SINGLE_SELECT":
            matches = typename == "ProjectV2SingleSelectField"
        else:
            matches = typename == "ProjectV2Field" and current.get("dataType") == expected_type
        if not matches:
            raise AuditError(f"Project field type differs: {name}")
    repositories = _obj(project.get("repositories"), "graphql.repositories")
    names = {
        _text(_obj(raw, "repository"), "nameWithOwner", "repository")
        for raw in _list(repositories.get("nodes"), "repositories.nodes")
    }
    linked = repository in names
    if not linked:
        raise AuditError("strict-audit Project is not linked to the repository")
    return ProjectEvidence(
        number,
        project_url,
        len(project_items),
        _integer(field_result, "totalCount", "project fields"),
        linked,
    )
