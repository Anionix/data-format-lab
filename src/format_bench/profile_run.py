from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .canonical import read_csv
from .claims.fastlanes import run_fastlanes_claim
from .claims.tsfile import run_tsfile_claim
from .claims.vortex import run_vortex_stress
from .formats.lance import build_fts, query_fts
from .json_contract import strict_json_dumps
from .model import Comparability, ExecutionState, Lane, TargetTier, transition
from .prompt import token_metrics, write_prompt_artifacts
from .research import load_research_records
from .runner import environment_info


def _load(run_dir: Path) -> tuple[dict, dict]:
    run = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if run["state"] != ExecutionState.ROUNDTRIP_VERIFIED:
        raise ValueError("profile run requires a round-trip verified run directory")
    dataset = json.loads(
        (run_dir / run["input"]["manifest"]).read_text(encoding="utf-8")
    )
    return run, dataset


def _finish(root: Path, run_dir: Path, run: dict, profile: Lane, evidence: dict) -> Path:
    results = {
        "schema_version": "1",
        "run_id": run_dir.name,
        "dataset_id": run["dataset_id"],
        "profile": profile,
        "state": ExecutionState.BENCHMARKED,
        "seed": run["seed"],
        "environment": environment_info(root),
        "results": evidence,
    }
    path = run_dir / "results.json"
    path.write_text(strict_json_dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run["state"] = transition(ExecutionState.ROUNDTRIP_VERIFIED, ExecutionState.BENCHMARKED)
    run["profile"] = profile
    (run_dir / "manifest.json").write_text(
        strict_json_dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _attempt(
    comparability: Comparability,
    invoke: Callable[[], dict],
    target_tier: TargetTier = TargetTier.CORE,
) -> dict:
    base = {
        "lane": Lane.CLAIMS,
        "comparability": comparability,
        "target_tier": target_tier,
        "failure_reason": None,
    }
    try:
        evidence = invoke()
        returned_status = evidence.get("status")
        if returned_status in {ExecutionState.FAILED, ExecutionState.UNSUPPORTED}:
            return {
                **base,
                "state": ExecutionState(returned_status),
                "failure_reason": evidence.get("reason", f"claim returned {returned_status}"),
                "evidence": evidence,
            }
        state = transition(ExecutionState.DISCOVERED, ExecutionState.ENCODED)
        state = transition(state, ExecutionState.ROUNDTRIP_VERIFIED)
        state = transition(state, ExecutionState.BENCHMARKED)
        return {**base, "state": state, "evidence": evidence}
    except (ImportError, ModuleNotFoundError) as error:
        return {**base, "state": ExecutionState.UNSUPPORTED, "failure_reason": str(error)}
    except Exception as error:
        return {
            **base,
            "state": ExecutionState.FAILED,
            "failure_reason": f"{type(error).__name__}: {error}",
        }


def run_claims(
    root: Path,
    run_dir: Path,
    *,
    stress_rows: int = 466_200,
    ts_devices: int = 100,
    ts_points: int = 10_000,
    warmups: int = 5,
    iterations: int = 30,
) -> Path:
    run, dataset = _load(run_dir)
    table = read_csv(run_dir / run["input"]["source"], dataset)
    if run["fixture"]:
        stress_rows = table.num_rows * 2
        ts_devices, ts_points = 2, 10
        warmups, iterations = 0, 1
    claims_dir = run_dir / "claims"
    claims_dir.mkdir()

    def lance_claim() -> dict:
        path = claims_dir / "lance-fts.lance"
        built = build_fts(table, path)
        artifact = built.pop("artifact")
        return {
            **built,
            "artifact": str(path.relative_to(run_dir)),
            "native_bytes": artifact.native_bytes,
            "transport_zstd_bytes": artifact.transport_zstd_bytes,
            "searches": {
                query: query_fts(
                    path, table, query, warmups=warmups, iterations=iterations
                )
                for query in ("agent", "database", "swift")
            },
        }

    evidence = {
        "lance_fts": _attempt(Comparability.FULL_COMPARABLE, lance_claim),
        "vortex_stress": _attempt(
            Comparability.FULL_COMPARABLE,
            lambda: run_vortex_stress(
                table,
                claims_dir / "vortex-stress",
                rows=stress_rows,
                warmups=warmups,
                iterations=iterations,
                seed=run["seed"],
            ),
        ),
        "tsfile_time_series": _attempt(
            Comparability.ADAPTED,
            lambda: run_tsfile_claim(
                claims_dir / "tsfile-time-series",
                devices=ts_devices,
                points_per_device=ts_points,
                warmups=min(3, warmups),
                iterations=min(10, iterations),
            ),
            TargetTier.EXPERIMENTAL,
        ),
        "fastlanes_official": _attempt(
            Comparability.PARTIAL,
            lambda: run_fastlanes_claim(
                claims_dir / "fastlanes-official",
                numeric_rows=1024 if run["fixture"] else 1_000_000,
                timeout_seconds=30 if run["fixture"] else 900,
            ),
            TargetTier.EXPERIMENTAL,
        ),
        "negative_research": load_research_records(root),
    }
    return _finish(root, run_dir, run, Lane.CLAIMS, evidence)


def run_prompt(root: Path, run_dir: Path) -> Path:
    run, dataset = _load(run_dir)
    table = read_csv(run_dir / run["input"]["source"], dataset)
    paths = write_prompt_artifacts(table, run_dir / "prompt")
    state = transition(ExecutionState.DISCOVERED, ExecutionState.ENCODED)
    state = transition(state, ExecutionState.ROUNDTRIP_VERIFIED)
    state = transition(state, ExecutionState.BENCHMARKED)
    evidence = {
        "prompt_v1": {
            "lane": Lane.PROMPT,
            "comparability": Comparability.FULL_COMPARABLE,
            "state": state,
            "artifacts": {name: str(path.relative_to(run_dir)) for name, path in paths.items()},
            "metrics": token_metrics(table, paths),
            "failure_reason": None,
        }
    }
    return _finish(root, run_dir, run, Lane.PROMPT, evidence)
