from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pyarrow as pa

from format_bench.canonical import canonical_hash, query_counts, read_csv
from format_bench.model import (
    ExecutionState,
    Lane,
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
)
from format_bench.profile_run import _finish, _load
from format_bench.robustness.cases import generated_cases, materialize_case, named_cases
from format_bench.robustness.evidence import ArtifactBudgetExceeded, EvidenceStore
from format_bench.robustness.paths import reject_symlink_tree
from format_bench.robustness.runner import run_case
from format_bench.robustness.targets import (
    RobustnessTarget,
    core_targets,
    encode_malformed,
    encode_valid,
)


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _manifest(dataset: dict, table: pa.Table) -> dict:
    return {
        **dataset,
        "rows": table.num_rows,
        "canonical_hash": canonical_hash(table),
        "expected_counts": query_counts(table),
    }


def _ipc(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    with pa.ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


def _artifact_files(path: Path) -> list[Path]:
    reject_symlink_tree(path, "staged artifact contains a symlink")
    files = (
        [path]
        if path.is_file()
        else sorted(item for item in path.rglob("*") if item.is_file())
    )
    if not files:
        raise ValueError("artifact has no regular files to mutate")
    return files


def _record(record) -> dict:
    return {
        "path": f"robustness/{record.relative_path}",
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
    }


def _execute(
    run_dir: Path,
    store: EvidenceStore,
    target: RobustnessTarget,
    case_id: str,
    expectation: RobustnessExpectation,
    table: pa.Table,
    dataset: dict,
    timeout: float,
    *,
    malformed: str | None = None,
) -> dict:
    with (
        tempfile.TemporaryDirectory() as temporary,
        tempfile.TemporaryDirectory(dir=run_dir) as process_directory,
    ):
        staging = Path(temporary)
        artifact = staging / f"artifact{target.adapter.describe().extension}"
        mutation = None
        if malformed in {"missing_column", "extra_column"}:
            encode_malformed(target, table, artifact, malformed)
        else:
            encode_valid(target, table, artifact)
            if malformed == "truncated_artifact":
                victim = _artifact_files(artifact)[0]
                data = victim.read_bytes()
                offset = len(data) // 2
                victim.write_bytes(data[:offset])
                member = (
                    victim.name
                    if artifact.is_file()
                    else victim.relative_to(artifact).as_posix()
                )
                mutation = {
                    "id": case_id,
                    "operation": "truncate",
                    "parameters": {"offset": offset},
                    "member": member,
                }

        prefix = Path("cases") / target.name / case_id
        input_record = store.store_bytes(prefix / "input.arrow", _ipc(table))
        manifest_record = store.store_bytes(
            prefix / "manifest.json", _json(_manifest(dataset, table))
        )
        artifact_records = store.import_path(artifact, prefix / artifact.name)
        request = {
            "schema_version": "1",
            "contract_version": "1",
            "case_id": case_id,
            "target": target.name,
            "expectation": expectation,
            "manifest": f"robustness/{manifest_record.relative_path}",
            "artifact": f"robustness/{prefix.as_posix()}/{artifact.name}",
        }
        if mutation is not None:
            request["mutation"] = mutation
        request_record = store.store_bytes(prefix / "request.json", _json(request))
        output = Path(process_directory) / "process"
        result = run_case(
            run_dir,
            f"robustness/{request_record.relative_path}",
            output.relative_to(run_dir),
            timeout,
        )
        stdout = store.store_bytes(prefix / "stdout.txt", (run_dir / result["stdout"]).read_bytes())
        stderr = store.store_bytes(prefix / "stderr.txt", (run_dir / result["stderr"]).read_bytes())
    result.update(
        schema_version="1",
        contract_version="1",
        tier=target.tier,
        input_canonical_hash=canonical_hash(table),
        input_arrow=_record(input_record),
        stdout=f"robustness/{stdout.relative_path}",
        stderr=f"robustness/{stderr.relative_path}",
        artifact_records=[_record(item) for item in artifact_records],
    )
    store.store_bytes(prefix / "result.json", _json(result))
    return result


def _incomplete(target, case_id, expectation, observed, error) -> dict:
    return {
        "schema_version": "1",
        "contract_version": "1",
        "case_id": case_id,
        "target": target.name,
        "tier": target.tier,
        "expectation": expectation,
        "observed": observed,
        "verdict": RobustnessVerdict.INCOMPLETE,
        "details": {"error_type": type(error).__name__, "message": str(error)[-500:]},
    }


def run_bounded(
    root: Path,
    run_dir: Path,
    *,
    seed: int = 20260703,
    generated_count: int = 32,
    timeout_seconds: float = 30,
    artifact_budget_mib: int = 1024,
    targets: tuple[RobustnessTarget, ...] | None = None,
) -> Path:
    run, dataset = _load(run_dir)
    base = read_csv(run_dir / run["input"]["source"], dataset)
    cases = list(named_cases()) + list(generated_cases(seed, generated_count))
    if run["fixture"]:
        keep = {"rows-1", "malformed-missing-column", "malformed-truncated"}
        cases = [
            case
            for case in cases
            if case.case_id in keep or case.case_id.startswith("generated-000-")
        ]
    store = EvidenceStore(run_dir / "robustness", artifact_budget_mib * 1024 * 1024)
    observations: list[dict] = []
    exhausted = False
    for target in targets or core_targets():
        for case in cases:
            case_id = case.case_id
            expectation = case.expectation
            try:
                table = (
                    base
                    if expectation is not RobustnessExpectation.MUST_ROUNDTRIP
                    else materialize_case(base, case)
                )
                observations.append(
                    _execute(
                        run_dir,
                        store,
                        target,
                        case_id,
                        expectation,
                        table,
                        dataset,
                        timeout_seconds,
                        malformed=(
                            None
                            if expectation is RobustnessExpectation.MUST_ROUNDTRIP
                            else case.category
                        ),
                    )
                )
            except ArtifactBudgetExceeded as error:
                observations.append(_incomplete(
                    target, case_id, expectation,
                    ObservedOutcome.BUDGET_EXHAUSTED, error,
                ))
                exhausted = True
                break
            except (ImportError, ModuleNotFoundError) as error:
                observations.append(_incomplete(
                    target, case_id, expectation, ObservedOutcome.UNSUPPORTED, error,
                ))
            except Exception as error:
                observations.append(_incomplete(
                    target, case_id, expectation,
                    ObservedOutcome.HARNESS_FAILED, error,
                ))
        if exhausted:
            break
    summary = {verdict.value: 0 for verdict in RobustnessVerdict}
    for item in observations:
        summary[item["verdict"].value] += 1
    evidence = {
        "robustness_v1": {
            "contract_version": "1",
            "state": ExecutionState.BENCHMARKED,
            "suite": "bounded",
            "config": {
                "seed": seed,
                "generated_cases": generated_count,
                "effective_generated_cases": sum(
                    case.case_id.startswith("generated-") for case in cases
                ),
                "case_timeout_seconds": timeout_seconds,
                "artifact_budget_mib": artifact_budget_mib,
            },
            "cases": observations,
            "summary": summary,
        }
    }
    # LLM contract: ROUNDTRIP_VERIFIED -> BENCHMARKED; report performs -> REPORTED.
    return _finish(root, run_dir, run, Lane.ROBUSTNESS, evidence)
