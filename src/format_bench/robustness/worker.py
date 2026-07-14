from __future__ import annotations

import argparse
import json
from pathlib import Path

from format_bench.model import ObservedOutcome, RobustnessExpectation
from format_bench.registry import adapter_map
from format_bench.robustness.paths import reject_symlink_tree
from format_bench.robustness.targets import read_robustness, target_map


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
    reject_symlink_tree(target, "robustness artifact tree contains a symlink")
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
    details = {}
    try:
        if expectation is RobustnessExpectation.MUST_ROUNDTRIP:
            effective_manifest = json.loads(manifest.read_text(encoding="utf-8"))
            adapter.read(artifact, effective_manifest)
            try:
                verification = adapter.verify_roundtrip(artifact, effective_manifest)
                observed = (
                    ObservedOutcome.ROUNDTRIP_EQUAL
                    if verification["passed"]
                    else ObservedOutcome.VALUE_MISMATCH
                )
            except ValueError as error:
                observed = ObservedOutcome.VALUE_MISMATCH
                details = {"error_type": type(error).__name__, "message": str(error)[-500:]}
        else:
            effective_manifest = json.loads(manifest.read_text(encoding="utf-8"))
            robustness_target = target_map().get(target)
            if robustness_target is None:
                adapter.read(artifact, effective_manifest)
            else:
                read_robustness(robustness_target, artifact, effective_manifest)
            observed = ObservedOutcome.ACCEPTED
    except ModuleNotFoundError as error:
        observed = ObservedOutcome.UNSUPPORTED
        return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": {"error_type": type(error).__name__}}
    except Exception as error:  # Target errors are evidence, not parent-process failures.
        observed = ObservedOutcome.REJECTED
        return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": {"error_type": type(error).__name__, "message": str(error)[-500:]}}
    return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": details}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_request(args.request), separators=(",", ":")))


if __name__ == "__main__":
    main()
