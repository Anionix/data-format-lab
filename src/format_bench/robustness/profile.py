from __future__ import annotations

import hashlib
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
from format_bench.robustness.cases import CaseSpec, generated_cases, materialize_case, named_cases
from format_bench.robustness.evidence import ArtifactBudgetExceeded, ArtifactRecord, EvidenceStore
from format_bench.robustness.mutations import apply_mutation, mutation_recipes
from format_bench.robustness.paths import reject_symlink_tree
from format_bench.robustness.runner import MAX_WORKER_DETAILS_BYTES, run_case
from format_bench.robustness.targets import (
    RobustnessTarget,
    core_targets,
    encode_malformed,
    encode_valid,
)

_PER_CASE_OUTPUT_BUDGET_BYTES = 1024 * 1024


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


def _mutate(path: Path, seed: int, count: int, index: int):
    victim = _artifact_files(path)[0]
    data = victim.read_bytes()
    recipe = mutation_recipes(len(data), seed, count)[index]
    mutated = apply_mutation(data, recipe)
    victim.write_bytes(mutated)
    member = victim.name if path.is_file() else victim.relative_to(path).as_posix()
    return recipe, member, {
        "member_size_bytes": len(data),
        "before_sha256": hashlib.sha256(data).hexdigest(),
        "after_sha256": hashlib.sha256(mutated).hexdigest(),
    }


def _record(record) -> dict:
    return {
        "path": f"robustness/{record.relative_path}",
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
    }


def _case_result_reserve(
    prefix: Path,
    target: RobustnessTarget,
    case_id: str,
    expectation: RobustnessExpectation,
    input_record: ArtifactRecord,
    artifact_records: tuple[ArtifactRecord, ...],
    mutation: dict[str, object] | None,
    timeout: float,
    output_budget_bytes: int,
) -> int:
    placeholder = {
        "case_id": case_id,
        "target": target.name,
        "expectation": expectation,
        "observed": ObservedOutcome.BUDGET_EXHAUSTED,
        "verdict": RobustnessVerdict.NOT_APPLICABLE,
        "details": {"message": "x" * MAX_WORKER_DETAILS_BYTES},
        "process": {
            "exit_code": -(2**63),
            "signal": 2**31 - 1,
            "timed_out": True,
            "duration_ms": max(timeout * 1000 + 1000, 1_000_000_000_000),
            # fstat() can report the full spool size even when retained tails are capped.
            "stdout_bytes": 2**63 - 1,
            "stderr_bytes": 2**63 - 1,
            "stdout_truncated": True,
            "stderr_truncated": True,
            "output_budget_bytes": output_budget_bytes,
            "output_exhausted": True,
        },
        "stdout": f"robustness/{prefix.as_posix()}/stdout.txt",
        "stderr": f"robustness/{prefix.as_posix()}/stderr.txt",
        "schema_version": "1",
        "contract_version": "1",
        "tier": target.tier,
        "input_canonical_hash": "0" * 64,
        "input_arrow": _record(input_record),
        "artifact_records": [_record(item) for item in artifact_records],
        **({"mutation": mutation} if mutation is not None else {}),
    }
    return len(_json(placeholder))


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
    mutation_index: int | None = None,
    mutation_count: int = 0,
    seed: int = 0,
) -> dict[str, object]:
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
            elif mutation_index is not None:
                recipe, member, digests = _mutate(
                    artifact, seed, mutation_count, mutation_index
                )
                case_id = f"mutation-{mutation_index:03d}-{recipe.operation}"
                mutation = {
                    "id": case_id,
                    "recipe_id": recipe.mutation_id,
                    "operation": recipe.operation,
                    "parameters": recipe.options,
                    "member": member,
                    **digests,
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
        remaining = store.budget_bytes - store.used_bytes
        result_reserve = _case_result_reserve(
            prefix,
            target,
            case_id,
            expectation,
            input_record,
            artifact_records,
            mutation,
            timeout,
            _PER_CASE_OUTPUT_BUDGET_BYTES,
        )
        if remaining < result_reserve:
            raise ArtifactBudgetExceeded(
                "artifact budget exhausted before worker launch: "
                f"required reserve {result_reserve}, remaining {remaining}"
            )
        output_budget_bytes = min(
            _PER_CASE_OUTPUT_BUDGET_BYTES,
            remaining - result_reserve,
        )
        result = run_case(
            run_dir,
            f"robustness/{request_record.relative_path}",
            output.relative_to(run_dir),
            timeout,
            output_budget_bytes=output_budget_bytes,
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
    if mutation is not None:
        result["mutation"] = mutation
    store.store_bytes(prefix / "result.json", _json(result))
    return dict(result)


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
    mutations_per_target: int = 64,
    timeout_seconds: float = 30,
    artifact_budget_mib: int = 1024,
    targets: tuple[RobustnessTarget, ...] | None = None,
) -> Path:
    if mutations_per_target < 0:
        raise ValueError("mutations_per_target must be non-negative")
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
    mutation_count = min(mutations_per_target, 1) if run["fixture"] else mutations_per_target
    store = EvidenceStore(run_dir / "robustness", artifact_budget_mib * 1024 * 1024)
    observations: list[dict] = []
    exhausted = False
    for target in targets or core_targets():
        work: list[tuple[CaseSpec | None, int | None]] = [(case, None) for case in cases]
        work.extend((None, index) for index in range(mutation_count))
        for case, mutation_index in work:
            case_id = case.case_id if case else f"mutation-{mutation_index:03d}"
            expectation = (
                case.expectation
                if case
                else RobustnessExpectation.MUST_NOT_CRASH
            )
            try:
                if (
                    mutation_index is not None
                    or expectation is not RobustnessExpectation.MUST_ROUNDTRIP
                ):
                    table = base
                else:
                    assert case is not None
                    table = materialize_case(base, case)
                malformed = None
                if (
                    case is not None
                    and mutation_index is None
                    and expectation is not RobustnessExpectation.MUST_ROUNDTRIP
                ):
                    malformed = case.category
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
                        malformed=malformed,
                        mutation_index=mutation_index,
                        mutation_count=mutation_count,
                        seed=seed,
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
                "mutations_per_target": mutations_per_target,
                "effective_mutations_per_target": mutation_count,
                "case_timeout_seconds": timeout_seconds,
                "artifact_budget_mib": artifact_budget_mib,
            },
            "cases": observations,
            "summary": summary,
        }
    }
    # LLM contract: ROUNDTRIP_VERIFIED -> BENCHMARKED; report performs -> REPORTED.
    return _finish(root, run_dir, run, Lane.ROBUSTNESS, evidence)
