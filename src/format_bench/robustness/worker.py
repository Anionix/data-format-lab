from __future__ import annotations

import argparse
import json
from pathlib import Path

from format_bench.model import ObservedOutcome, RobustnessExpectation
from format_bench.json_contract import strict_json_dumps
from format_bench.registry import adapter_map
from format_bench.robustness.paths import reject_symlink_tree
from format_bench.robustness.targets import (
    TargetExecutionError,
    read_robustness,
    read_target,
    target_map,
)


# LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
# Worker setup failures are HARNESS_FAILED; only TargetExecutionError is REJECTED.


def _error_details(error: Exception) -> dict[str, object]:
    return {
        "error_type": type(error).__name__,
        "message": str(error)[-500:],
    }


def _harness_failure(case_id: str, error: Exception) -> dict:
    return {
        "schema_version": "1",
        "case_id": case_id,
        "observed": ObservedOutcome.HARNESS_FAILED,
        "details": _error_details(error),
    }


def _rejected(case_id: str, error: TargetExecutionError) -> dict:
    return {
        "schema_version": "1",
        "case_id": case_id,
        "observed": ObservedOutcome.REJECTED,
        "details": _error_details(error.cause),
    }


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
    request: object = None
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        case_id = request["case_id"]
        target = request["target"]
        expectation = RobustnessExpectation(request["expectation"])
        manifest = _safe(root, request["manifest"])
        artifact = _safe(root, request["artifact"])
        adapter = adapter_map()[target]
        effective_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        robustness_target = (
            target_map().get(target)
            if expectation is not RobustnessExpectation.MUST_ROUNDTRIP
            else None
        )
    except Exception as error:
        case_id = request.get("case_id", "unknown") if isinstance(request, dict) else "unknown"
        return _harness_failure(str(case_id), error)
    details = {}
    try:
        if expectation is RobustnessExpectation.MUST_ROUNDTRIP:
            try:
                read_target(adapter, artifact, effective_manifest)
            except ModuleNotFoundError as error:
                return {
                    "schema_version": "1",
                    "case_id": case_id,
                    "observed": ObservedOutcome.UNSUPPORTED,
                    "details": {"error_type": type(error).__name__},
                }
            except TargetExecutionError as error:
                return _rejected(case_id, error)
            try:
                verification = adapter.verify_roundtrip(artifact, effective_manifest)
                observed = (
                    ObservedOutcome.ROUNDTRIP_EQUAL
                    if verification["passed"]
                    else ObservedOutcome.VALUE_MISMATCH
                )
            except ModuleNotFoundError as error:
                return {
                    "schema_version": "1",
                    "case_id": case_id,
                    "observed": ObservedOutcome.UNSUPPORTED,
                    "details": {"error_type": type(error).__name__},
                }
            except ValueError as error:
                observed = ObservedOutcome.VALUE_MISMATCH
                details = {
                    "error_type": type(error).__name__,
                    "message": str(error)[-500:],
                }
            except Exception as error:
                observed = ObservedOutcome.HARNESS_FAILED
                details = {"error_type": type(error).__name__, "message": str(error)[-500:]}
        else:
            if robustness_target is None:
                read_target(adapter, artifact, effective_manifest)
            else:
                read_robustness(robustness_target, artifact, effective_manifest)
            observed = ObservedOutcome.ACCEPTED
    except ModuleNotFoundError as error:
        observed = ObservedOutcome.UNSUPPORTED
        return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": {"error_type": type(error).__name__}}
    except TargetExecutionError as error:
        return _rejected(case_id, error)
    except Exception as error:
        return _harness_failure(case_id, error)
    return {"schema_version": "1", "case_id": case_id, "observed": observed, "details": details}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    print(strict_json_dumps(run_request(args.request), separators=(",", ":")))


if __name__ == "__main__":
    main()
