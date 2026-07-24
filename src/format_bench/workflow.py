from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal, NotRequired, TypedDict

from .artifact_digest import artifact_sha256
from .canonical import canonical_hash, query_counts, read_csv, verify_table
from .datasets import load_manifest
from .formats.base import Artifact, FormatAdapter
from .model import ExecutionState, transition
from .registry import adapter_map, adapters
from .runner import environment_info


class SizeAttempt(TypedDict):
    index: int
    status: Literal["MEASURED", "FAILED"]
    native_bytes: NotRequired[int]
    transport_zstd_bytes: NotRequired[int]
    artifact_sha256: NotRequired[str]
    roundtrip_verified: NotRequired[bool]
    failure_reason: NotRequired[str]


class SizeObservations(TypedDict):
    contract_version: Literal["1"]
    resampling_unit: Literal["same_process_encode_invocation"]
    attempted: int
    completed: int
    attempts: list[SizeAttempt]


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_manifest(manifest: dict, table, source: Path) -> dict:
    effective = dict(manifest)
    effective.update(
        {
            "fixture": True,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "canonical_hash": canonical_hash(table),
            "rows": table.num_rows,
        }
    )
    effective["expected_counts"] = query_counts(table, effective)
    return effective


def _default_run_dir(root: Path, dataset_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return root / "runs" / f"{dataset_id}-{stamp}"


def _measured_size_attempt(
    index: int, artifact: Artifact, *, verified: bool
) -> SizeAttempt:
    return {
        "index": index,
        "status": "MEASURED",
        "native_bytes": artifact.native_bytes,
        "transport_zstd_bytes": artifact.transport_zstd_bytes,
        "artifact_sha256": artifact_sha256(artifact.path),
        "roundtrip_verified": verified,
    }


def _remove_artifact(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def prepare_run(
    root: Path,
    dataset_id: str,
    run_dir: Path | None = None,
    *,
    fixture: bool = False,
    selected: Iterable[FormatAdapter] | None = None,
    size_observations: int = 1,
) -> Path:
    if size_observations < 1:
        raise ValueError("size_observations must be positive")
    manifest = load_manifest(root, dataset_id)
    source = (
        root / "datasets" / dataset_id / "fixture.csv"
        if fixture
        else root / ".data" / dataset_id / "source.csv"
    )
    if not fixture:
        actual_source_sha256 = _sha256(source)
        if actual_source_sha256 != manifest["source_sha256"]:
            raise ValueError(
                "source SHA-256 mismatch: "
                f"expected {manifest['source_sha256']}, got {actual_source_sha256}"
            )
    destination = run_dir or _default_run_dir(root, dataset_id)
    destination.mkdir(parents=True, exist_ok=False)
    input_dir = destination / "input"
    input_dir.mkdir()

    table = read_csv(source, manifest)
    effective = _fixture_manifest(manifest, table, source) if fixture else manifest
    verify_table(table, effective)
    shutil.copy2(source, input_dir / "source.csv")
    _write_json(input_dir / "manifest.json", effective)

    entries = []
    observation_root = destination / ".size-observations"
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    # Active evidence may terminate as UNSUPPORTED or FAILED; terminal evidence never ranks.
    try:
        for adapter in adapters() if selected is None else selected:
            description = adapter.describe()
            artifact_path = destination / "artifacts" / (
                description.name + description.extension
            )
            observations: SizeObservations = {
                "contract_version": "1",
                "resampling_unit": "same_process_encode_invocation",
                "attempted": size_observations,
                "completed": 0,
                "attempts": [],
            }
            entry = {
                "format": description.name,
                "lane": description.lane,
                "comparability": description.comparability,
                "settings": description.settings,
                "state": ExecutionState.DISCOVERED,
                "artifact": str(artifact_path.relative_to(destination)),
                "failure_reason": None,
                "size_observations": observations,
            }
            attempt_index = 0
            try:
                artifact = adapter.encode(table, artifact_path)
                observations["attempts"].append(
                    _measured_size_attempt(0, artifact, verified=False)
                )
                observations["completed"] += 1
                for attempt_index in range(1, size_observations):
                    repeated_path = observation_root / description.name / (
                        f"{attempt_index}{description.extension}"
                    )
                    try:
                        repeated = adapter.encode(table, repeated_path)
                        verification = adapter.verify_roundtrip(repeated_path, effective)
                        if verification.get("passed") is not True:
                            raise ValueError("repeated encoding round-trip did not pass")
                        observations["attempts"].append(
                            _measured_size_attempt(
                                attempt_index, repeated, verified=True
                            )
                        )
                        observations["completed"] += 1
                    finally:
                        _remove_artifact(repeated_path)
                entry.update(
                    {
                        "state": transition(
                            ExecutionState.DISCOVERED, ExecutionState.ENCODED
                        ),
                        "native_bytes": artifact.native_bytes,
                        "transport_zstd_bytes": artifact.transport_zstd_bytes,
                        "prepare_write_ms": artifact.prepare_write_ms,
                    }
                )
            except (ImportError, ModuleNotFoundError) as error:
                _remove_artifact(artifact_path)
                observations["attempts"].append(
                    {
                        "index": attempt_index,
                        "status": "FAILED",
                        "failure_reason": f"{type(error).__name__}: {error}",
                    }
                )
                entry.update(
                    state=ExecutionState.UNSUPPORTED, failure_reason=str(error)
                )
            except Exception as error:  # Evidence must preserve adapter failures verbatim.
                _remove_artifact(artifact_path)
                observations["attempts"].append(
                    {
                        "index": attempt_index,
                        "status": "FAILED",
                        "failure_reason": f"{type(error).__name__}: {error}",
                    }
                )
                entry.update(
                    state=ExecutionState.FAILED,
                    failure_reason=f"{type(error).__name__}: {error}",
                )
            entries.append(entry)
    finally:
        if observation_root.exists():
            shutil.rmtree(observation_root)

    run_manifest = {
        "schema_version": "1",
        "dataset_id": dataset_id,
        "fixture": fixture,
        "rankable": not fixture,
        "state": ExecutionState.ENCODED,
        "seed": 20260703,
        "environment": environment_info(root),
        "input": {"source": "input/source.csv", "manifest": "input/manifest.json"},
        "formats": entries,
    }
    _write_json(destination / "manifest.json", run_manifest)
    return destination


def verify_run(run_dir: Path, selected: dict[str, FormatAdapter] | None = None) -> Path:
    manifest_path = run_dir / "manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset_manifest = json.loads(
        (run_dir / run_manifest["input"]["manifest"]).read_text(encoding="utf-8")
    )
    registered = selected or adapter_map()
    if not run_manifest["formats"]:
        # LLM contract: empty verification selection transitions ENCODED -> FAILED with a failure reason.
        run_manifest["state"] = transition(
            ExecutionState.ENCODED, ExecutionState.FAILED
        )
        run_manifest["failure_reason"] = "no adapters selected for verification"
        _write_json(manifest_path, run_manifest)
        return manifest_path
    # LLM contract: only ENCODED evidence can advance to ROUNDTRIP_VERIFIED here.
    for entry in run_manifest["formats"]:
        if entry["state"] != ExecutionState.ENCODED:
            continue
        try:
            verification = registered[entry["format"]].verify_roundtrip(
                run_dir / entry["artifact"], dataset_manifest
            )
            entry["verification"] = verification
            if verification.get("passed") is not True:
                raise ValueError("round-trip verification did not pass")
            if "size_observations" in entry:
                first_attempt = entry["size_observations"]["attempts"][0]
                if first_attempt.get("artifact_sha256") != artifact_sha256(
                    run_dir / entry["artifact"]
                ):
                    raise ValueError(
                        "verified artifact differs from encoded size evidence"
                    )
                first_attempt["roundtrip_verified"] = True
            entry["state"] = transition(
                ExecutionState.ENCODED, ExecutionState.ROUNDTRIP_VERIFIED
            )
        except Exception as error:
            entry["state"] = ExecutionState.FAILED
            entry["failure_reason"] = f"{type(error).__name__}: {error}"

    terminal = {
        ExecutionState.ROUNDTRIP_VERIFIED,
        ExecutionState.UNSUPPORTED,
        ExecutionState.FAILED,
    }
    if run_manifest["formats"] and all(
        entry["state"] in terminal for entry in run_manifest["formats"]
    ):
        # LLM contract: ENCODED -> ROUNDTRIP_VERIFIED requires every adapter to
        # be terminal and at least one adapter to complete round-trip verification;
        # an all-failure run remains terminal failure evidence.
        if any(
            entry["state"] == ExecutionState.ROUNDTRIP_VERIFIED
            for entry in run_manifest["formats"]
        ):
            run_manifest["state"] = ExecutionState.ROUNDTRIP_VERIFIED
        elif any(
            entry["state"] == ExecutionState.FAILED
            for entry in run_manifest["formats"]
        ):
            run_manifest["state"] = ExecutionState.FAILED
        else:
            run_manifest["state"] = ExecutionState.UNSUPPORTED
    _write_json(manifest_path, run_manifest)
    return manifest_path
