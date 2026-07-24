"""Check or explicitly synchronize review-closeout labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from audit_github import (
    AuditError, GitHubRest, Mutation, flatten_pages, label_spec, object_list, object_map,
    object_text,
)
from github_labels import LabelSpec, plan_labels

MANIFEST = Path(__file__).parents[1] / "docs/agents/review-closeout-labels.json"
TARGETS = frozenset({"Anionix/data-format-lab", "Anionix/diagnostic-triage"})
LabelSyncError = AuditError


def _strings(value: object, context: str) -> tuple[str, ...]:
    items = object_list(value, context)
    if not all(isinstance(item, str) and item for item in items):
        raise AuditError(f"{context} must contain non-empty strings")
    return tuple(cast(list[str], items))


def load_manifest() -> tuple[tuple[str, ...], frozenset[str], tuple[LabelSpec, ...]]:
    try:
        raw = object_map(json.loads(MANIFEST.read_text()), "label manifest")
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read label manifest: {error}") from error
    if object_text(raw, "schema_version", "label manifest") != "review-closeout-labels/v1":
        raise AuditError("unsupported label manifest")
    repositories = _strings(raw.get("repositories"), "repositories")
    if frozenset(repositories) != TARGETS or len(repositories) != len(TARGETS):
        raise AuditError("manifest repositories do not match allowed targets")
    required_raw = _strings(raw.get("required_existing"), "required_existing")
    required = frozenset(name.casefold() for name in required_raw)
    managed = tuple(label_spec(item) for item in object_list(raw.get("managed_labels"), "managed_labels"))
    managed_names = {item.name.casefold() for item in managed}
    if len(required) != len(required_raw) or len(managed_names) != len(managed):
        raise AuditError("label manifest contains duplicate names")
    if required & managed_names:
        raise AuditError("required and managed labels overlap")
    return repositories, required, managed


def _read_labels(client: GitHubRest, repository: str) -> tuple[LabelSpec, ...]:
    identity = object_map(client.get(f"repos/{repository}"), "repository")
    if object_text(identity, "full_name", "repository") != repository:
        raise AuditError(f"repository identity mismatch: {repository}")
    return tuple(
        label_spec(item)
        for item in flatten_pages(
            client.pages(f"repos/{repository}/labels?per_page=100"), "labels"
        )
    )


def _checked_plan(
    repository: str, required: frozenset[str], desired: tuple[LabelSpec, ...],
    current: tuple[LabelSpec, ...],
) -> tuple[Mutation, ...]:
    if missing := sorted(required - {item.name.casefold() for item in current}):
        raise AuditError(f"{repository}: missing required labels: {', '.join(missing)}")
    try:
        return tuple(
            Mutation(item.method, item.path, item.key, item.payload)
            for item in plan_labels(repository, desired, current)
        )
    except ValueError as error:
        raise AuditError(str(error)) from error


def synchronize(
    apply: bool, client: GitHubRest | None = None,
) -> dict[str, tuple[Mutation, ...]]:
    client = client or GitHubRest()
    repositories, required, desired = load_manifest()
    snapshots = {repository: _read_labels(client, repository) for repository in repositories}
    plans = {
        repository: _checked_plan(repository, required, desired, snapshots[repository])
        for repository in repositories
    }
    if not apply:
        return plans
    # LLM contract: DECLARED -> SNAPSHOTTED -> PLANNED -> APPLIED -> VERIFIED.
    for repository in repositories:
        for mutation in plans[repository]:
            try:
                client.mutate(mutation)
            except AuditError:
                remaining = _checked_plan(repository, required, desired, _read_labels(client, repository))
                if mutation.key.casefold() in {item.key.casefold() for item in remaining}:
                    raise
    for repository in repositories:
        if _checked_plan(repository, required, desired, _read_labels(client, repository)):
            raise AuditError(f"{repository}: label synchronization did not converge")
    return plans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        plans = synchronize(args.apply)
    except AuditError as error:
        print(f"review-closeout label sync failed: {error}")
        return 2
    print(
        json.dumps(
            {repository: len(plan) for repository, plan in plans.items()},
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0 if args.apply or not any(plans.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
