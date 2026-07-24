from __future__ import annotations

import re
from pathlib import Path
from typing import TypeGuard, cast

from .json_contract import strict_json_dumps, strict_json_loads
from .model import Comparability, ExecutionState


ResearchRecord = dict[str, object]
_FULL_GIT_SHA1 = re.compile(r"[0-9A-Fa-f]{40}\Z")


def _is_full_git_sha1(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and _FULL_GIT_SHA1.fullmatch(value) is not None


def _json_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{context} keys must be strings")
    return cast(dict[str, object], raw)


def _required_text(record: ResearchRecord, name: str, context: str) -> str:
    value = record.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} {name} must be a non-empty string")
    return value


def _source_commits(record: ResearchRecord, name: str) -> dict[str, str]:
    raw = _json_object(record.get("source_commits"), "research source_commits")
    commits: dict[str, str] = {}
    for source, commit in raw.items():
        if not source or not _is_full_git_sha1(commit):
            raise ValueError(f"research commit is not a full SHA: {name}")
        commits[source] = commit
    return commits


def load_research_records(root: Path) -> dict[str, ResearchRecord]:
    root = root.resolve()
    records: dict[str, ResearchRecord] = {}
    for path in sorted((root / "research" / "formats").glob("*.json")):
        # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
        # Invalid boundary data terminates FAILED before entering the record registry.
        record = _json_object(
            strict_json_loads(path.read_text(encoding="utf-8")),
            f"research record {path.name}",
        )
        name = _required_text(record, "name", "research record")
        if path.stem != name:
            raise ValueError(f"research filename does not match name: {path}")
        Comparability(_required_text(record, "comparability", f"research {name}"))
        state = ExecutionState(_required_text(record, "state", f"research {name}"))
        if state not in {ExecutionState.UNSUPPORTED, ExecutionState.FAILED}:
            raise ValueError(f"negative evidence must have a terminal state: {name}")
        record["source_commits"] = _source_commits(record, name)
        _required_text(record, "claim_summary", f"research {name}")
        if str(root) in strict_json_dumps(record):
            raise ValueError(f"research evidence leaks a local path: {name}")
        records[name] = record
    return records
