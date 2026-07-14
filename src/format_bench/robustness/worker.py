from __future__ import annotations

import argparse
import json
from pathlib import Path

from format_bench.model import ObservedOutcome, RobustnessExpectation
from format_bench.registry import adapter_map


def _safe(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("robustness paths must be safe relative paths")
    candidate = root / path
    if any(item.is_symlink() for item in (candidate, *candidate.parents) if item != root.parent):
        raise ValueError("robustness artifact path contains a symlink")
    target = candidate.resolve()
    if not target.is_relative_to(root.resolve()) or not target.exists():
        raise ValueError("robustness artifact path is missing or unsafe")
    return target


def run_request(request_path: Path) -> dict:
    root = Path.cwd().resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    case_id = request["case_id"]
    target = request["target"]
    expectation = RobustnessExpectation(request["expectation"])
    manifest = _safe(root, request["manifest"])
    artifact = _safe(root, request["artifact"])
    adapter = adapter_map()[target]
    try:
        if expectation is RobustnessExpectation.MUST_ROUNDTRIP:
            adapter.verify_roundtrip(artifact, json.loads(manifest.read_text(encoding="utf-8")))
            observed = ObservedOutcome.ROUNDTRIP_EQUAL
        else:
            adapter.read(artifact, json.loads(manifest.read_text(encoding="utf-8")))
            observed = ObservedOutcome.ACCEPTED
    except ModuleNotFoundError as error:
        observed = ObservedOutcome.UNSUPPORTED
        return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": {"error_type": type(error).__name__}}
    except Exception as error:  # Target errors are evidence, not parent-process failures.
        observed = ObservedOutcome.REJECTED
        return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": {"error_type": type(error).__name__, "message": str(error)[-500:]}}
    return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": {}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_request(args.request), separators=(",", ":")))


if __name__ == "__main__":
    main()
