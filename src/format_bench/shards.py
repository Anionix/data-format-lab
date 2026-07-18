from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import TypeAlias, cast

from .model import ExecutionState, transition

JSONValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | list["JSONValue"]
    | dict[str, "JSONValue"]
)
JSONObject = dict[str, JSONValue]


def _read_json(path: Path) -> JSONObject:
    raw: object = cast(object, json.loads(path.read_text(encoding="utf-8")))
    return _object(_json_value(raw, str(path)), str(path))


def _json_value(value: object, label: str) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item, label) for item in cast(list[object], value)]
    if isinstance(value, dict):
        result: dict[str, JSONValue] = {}
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise ValueError(f"JSON object key is not a string: {label}")
            result[key] = _json_value(item, f"{label}.{key}")
        return result
    raise ValueError(f"unsupported JSON value: {label}")


def _object(value: JSONValue, label: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {label}")
    return value


def _object_map(value: JSONValue, label: str) -> dict[str, JSONObject]:
    value = _object(value, label)
    return {key: _object(item, f"{label}.{key}") for key, item in value.items()}


def _write_json(path: Path, value: JSONObject) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hardlink_tree(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f"symlink is not allowed in shard input: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            _hardlink_tree(entry, target)
        elif entry.is_file():
            os.link(entry, target)
        else:
            raise ValueError(f"unsupported artifact entry: {entry}")


def _copy_run_files(base_run: Path, output_run: Path) -> None:
    output_run.mkdir(parents=True)
    for name in ("artifacts", "input"):
        _hardlink_tree(base_run / name, output_run / name)
    shutil.copy2(base_run / "manifest.json", output_run / "manifest.json")


def merge_equivalence_shards(
    base_run: Path, shard_root: Path, output_run: Path
) -> Path:
    """Merge independently measured pair runs without duplicating artifacts."""
    base_manifest = _read_json(base_run / "manifest.json")
    if base_manifest.get("state") != ExecutionState.ROUNDTRIP_VERIFIED:
        raise ValueError("base run must be round-trip verified")
    if output_run.exists():
        raise ValueError(f"output run already exists: {output_run}")

    shard_paths = sorted(path for path in shard_root.iterdir() if path.is_dir())
    if not shard_paths:
        raise ValueError("no shard directories found")
    merged_results: JSONObject = {}
    merged_pairs: JSONObject = {}
    shard_records: list[JSONValue] = []
    environments: list[JSONObject] = []
    for shard in shard_paths:
        manifest = _read_json(shard / "manifest.json")
        results = _read_json(shard / "results.json")
        if manifest.get("dataset_id") != base_manifest.get("dataset_id"):
            raise ValueError(f"dataset mismatch in shard: {shard}")
        if manifest.get("state") not in {
            ExecutionState.BENCHMARKED,
            ExecutionState.REPORTED,
        } or results.get("state") not in {
            ExecutionState.BENCHMARKED,
            ExecutionState.REPORTED,
        }:
            raise ValueError(f"shard is not benchmarked: {shard}")
        if results.get("status") != "MEASURED":
            raise ValueError(f"shard is not fully measured: {shard}")
        for job_id, evidence in _object_map(
            results.get("results", {}), f"{shard}/results"
        ).items():
            if job_id in merged_results:
                raise ValueError(f"duplicate benchmark job: {job_id}")
            merged_results[job_id] = evidence
        equivalence = _object(results.get("equivalence", {}), f"{shard}/equivalence")
        pairs = _object_map(
            equivalence.get("pairs", {}), f"{shard}/equivalence.pairs"
        )
        for pair, evidence in pairs.items():
            if pair in merged_pairs:
                raise ValueError(f"duplicate equivalence pair: {pair}")
            merged_pairs[pair] = evidence
        environments.append(_object(results["environment"], f"{shard}/environment"))
        shard_records.append(
            {
                "path": str(shard.relative_to(shard_root)),
                "state": results["state"],
            }
        )

    if len({json.dumps(value, sort_keys=True) for value in environments}) != 1:
        raise ValueError("shard environments do not match")
    _copy_run_files(base_run, output_run)

    manifest = dict(base_manifest)
    manifest["state"] = transition(
        ExecutionState.ROUNDTRIP_VERIFIED, ExecutionState.BENCHMARKED
    )
    first_shard_results = _read_json(shard_paths[0] / "results.json")
    first_equivalence = _object(first_shard_results["equivalence"], "equivalence")
    equivalence_value: JSONObject = {
        "contract_version": "1",
        "bounds": _object(first_equivalence.get("bounds", {}), "equivalence.bounds"),
        "parallel_jobs": True,
        "shard_count": len(shard_paths),
        "pairs": merged_pairs,
    }
    manifest["equivalence"] = equivalence_value
    manifest["measurement"] = first_shard_results["measurement"]
    manifest["shards"] = shard_records
    formats = manifest.get("formats")
    if not isinstance(formats, list):
        raise ValueError("base manifest formats must be a list")
    for raw_entry in formats:
        entry = _object(raw_entry, "manifest.formats entry")
        name = entry.get("format")
        if not isinstance(name, str):
            raise ValueError("manifest format name must be a string")
        if any(job_id.startswith(f"{name}/") for job_id in merged_results):
            entry["state"] = transition(
                ExecutionState.ROUNDTRIP_VERIFIED, ExecutionState.BENCHMARKED
            )
    _write_json(output_run / "manifest.json", manifest)

    first_results = first_shard_results
    combined = dict(first_results)
    combined["run_id"] = output_run.name
    combined["state"] = ExecutionState.BENCHMARKED
    combined["status"] = "MEASURED"
    combined["results"] = merged_results
    combined["equivalence"] = manifest["equivalence"]
    combined["shards"] = shard_records
    _write_json(output_run / "results.json", combined)
    return output_run / "results.json"
