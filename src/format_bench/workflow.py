from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .canonical import canonical_hash, query_counts, read_csv, verify_table
from .datasets import load_manifest
from .formats.base import FormatAdapter
from .model import ExecutionState, transition
from .registry import adapter_map, adapters
from .runner import environment_info


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture_manifest(manifest: dict, table, source: Path) -> dict:
    effective = dict(manifest)
    effective.update(
        {
            "fixture": True,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "canonical_hash": canonical_hash(table),
            "rows": table.num_rows,
            "expected_counts": query_counts(table),
        }
    )
    return effective


def _default_run_dir(root: Path, dataset_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return root / "runs" / f"{dataset_id}-{stamp}"


def prepare_run(
    root: Path,
    dataset_id: str,
    run_dir: Path | None = None,
    *,
    fixture: bool = False,
    selected: Iterable[FormatAdapter] | None = None,
) -> Path:
    manifest = load_manifest(root, dataset_id)
    destination = run_dir or _default_run_dir(root, dataset_id)
    destination.mkdir(parents=True, exist_ok=False)
    input_dir = destination / "input"
    input_dir.mkdir()

    source = (
        root / "datasets" / dataset_id / "fixture.csv"
        if fixture
        else root / ".data" / dataset_id / "source.csv"
    )
    table = read_csv(source, manifest)
    effective = _fixture_manifest(manifest, table, source) if fixture else manifest
    verify_table(table, effective)
    shutil.copy2(source, input_dir / "source.csv")
    _write_json(input_dir / "manifest.json", effective)

    entries = []
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    # Active evidence may terminate as UNSUPPORTED or FAILED; terminal evidence never ranks.
    for adapter in selected or adapters():
        description = adapter.describe()
        artifact_path = destination / "artifacts" / (
            description.name + description.extension
        )
        entry = {
            "format": description.name,
            "lane": description.lane,
            "comparability": description.comparability,
            "settings": description.settings,
            "state": ExecutionState.DISCOVERED,
            "artifact": str(artifact_path.relative_to(destination)),
            "failure_reason": None,
        }
        try:
            artifact = adapter.encode(table, artifact_path)
            entry.update(
                {
                    "state": transition(ExecutionState.DISCOVERED, ExecutionState.ENCODED),
                    "native_bytes": artifact.native_bytes,
                    "transport_zstd_bytes": artifact.transport_zstd_bytes,
                    "prepare_write_ms": artifact.prepare_write_ms,
                }
            )
        except (ImportError, ModuleNotFoundError) as error:
            entry.update(state=ExecutionState.UNSUPPORTED, failure_reason=str(error))
        except Exception as error:  # Evidence must preserve adapter failures verbatim.
            entry.update(state=ExecutionState.FAILED, failure_reason=f"{type(error).__name__}: {error}")
        entries.append(entry)

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
    # LLM contract: only ENCODED evidence can advance to ROUNDTRIP_VERIFIED here.
    for entry in run_manifest["formats"]:
        if entry["state"] != ExecutionState.ENCODED:
            continue
        try:
            verification = registered[entry["format"]].verify_roundtrip(
                run_dir / entry["artifact"], dataset_manifest
            )
            entry["verification"] = verification
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
    if all(entry["state"] in terminal for entry in run_manifest["formats"]):
        run_manifest["state"] = ExecutionState.ROUNDTRIP_VERIFIED
    _write_json(manifest_path, run_manifest)
    return manifest_path
