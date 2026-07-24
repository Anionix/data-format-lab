from __future__ import annotations

import json
from pathlib import Path

from .json_contract import strict_json_dumps
from .model import Comparability, ExecutionState


def load_research_records(root: Path) -> dict[str, dict]:
    root = root.resolve()
    records = {}
    for path in sorted((root / "research" / "formats").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        name = record["name"]
        if path.stem != name:
            raise ValueError(f"research filename does not match name: {path}")
        Comparability(record["comparability"])
        state = ExecutionState(record["state"])
        if state not in {ExecutionState.UNSUPPORTED, ExecutionState.FAILED}:
            raise ValueError(f"negative evidence must have a terminal state: {name}")
        if any(len(commit) != 40 for commit in record["source_commits"].values()):
            raise ValueError(f"research commit is not a full SHA: {name}")
        if not isinstance(record.get("claim_summary"), str) or not record["claim_summary"]:
            raise ValueError(f"research claim summary is missing: {name}")
        if str(root) in strict_json_dumps(record):
            raise ValueError(f"research evidence leaks a local path: {name}")
        records[name] = record
    return records
