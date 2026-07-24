from __future__ import annotations

import json
import hashlib
import os
import shutil
from pathlib import Path
from typing import TypeAlias, cast

from .json_contract import strict_json_dumps
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
    path.write_text(strict_json_dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_run_path(
    run: Path, value: JSONValue, label: str, *, allow_missing: bool = False
) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"expected relative path: {label}")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"run path must be relative: {label}")
    candidate = run / relative
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise ValueError(f"run path must not resolve through a symlink: {label}")
    try:
        candidate.resolve(strict=not allow_missing).relative_to(run.resolve())
    except (FileNotFoundError, ValueError) as error:
        raise ValueError(f"run path is missing or escapes run directory: {label}") from error
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    def frame(kind: bytes, value: bytes = b"") -> None:
        digest.update(kind)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    def add_file(file_path: Path) -> None:
        digest.update(file_path.stat().st_size.to_bytes(8, "big"))
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)

    if path.is_file():
        frame(b"root-file")
        add_file(path)
    elif path.is_dir():
        frame(b"root-directory")
        for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
            relative = child.relative_to(path).as_posix().encode("utf-8")
            if child.is_symlink():
                raise ValueError(f"artifact directory contains a symlink: {child}")
            if child.is_dir():
                frame(b"directory-entry", relative)
            elif child.is_file():
                frame(b"file-entry", relative)
                add_file(child)
            else:
                raise ValueError(f"unsupported artifact entry: {child}")
    else:
        raise ValueError(f"artifact path is neither a file nor directory: {path}")
    return digest.hexdigest()


def _format_identities(run: Path, manifest: JSONObject) -> dict[str, JSONObject]:
    formats = manifest.get("formats")
    if not isinstance(formats, list):
        raise ValueError("manifest formats must be a list")
    identities: dict[str, JSONObject] = {}
    for raw_entry in formats:
        entry = _object(raw_entry, "manifest.formats entry")
        name = entry.get("format")
        if not isinstance(name, str) or name in identities:
            raise ValueError("manifest format names must be unique strings")
        terminal_without_artifact = entry.get("state") in {
            ExecutionState.UNSUPPORTED,
            ExecutionState.FAILED,
        }
        artifact = _safe_run_path(
            run,
            entry.get("artifact"),
            f"{name}.artifact",
            allow_missing=terminal_without_artifact,
        )
        state = entry.get("state")
        active_state = state in {
            ExecutionState.ROUNDTRIP_VERIFIED,
            ExecutionState.BENCHMARKED,
            ExecutionState.REPORTED,
        }
        # LLM contract: ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED advances
        # active evidence without changing identity; pre-artifact states are rejected.
        if not terminal_without_artifact and not active_state:
            raise ValueError(f"{name}.state is not verified for shard identity")
        identity_state = state if terminal_without_artifact else None
        identity_failure = (
            entry.get("failure_reason") if terminal_without_artifact else None
        )
        identities[name] = {
            "artifact": entry["artifact"],
            "lane": entry.get("lane"),
            "comparability": entry.get("comparability"),
            "settings": entry.get("settings"),
            "state": identity_state,
            "failure_reason": identity_failure,
            "native_bytes": entry.get("native_bytes"),
            "transport_zstd_bytes": entry.get("transport_zstd_bytes"),
            "artifact_sha256": _sha256(artifact) if artifact.exists() else None,
        }
    return identities


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
    base_input_spec = _object(base_manifest.get("input"), "input")
    base_input_manifest_path = _safe_run_path(
        base_run, base_input_spec.get("manifest"), "input.manifest"
    )
    base_source = _safe_run_path(base_run, "input/source.csv", "input/source.csv")
    base_input_manifest = _read_json(base_input_manifest_path)
    base_formats = _format_identities(base_run, base_manifest)
    base_source_sha256 = _sha256(base_source)
    merged_results: JSONObject = {}
    merged_pairs: JSONObject = {}
    shared_job_ids: list[JSONValue] = []
    shard_records: list[JSONValue] = []
    environments: list[JSONObject] = []
    measurements: list[JSONObject] = []
    equivalence_contracts: list[JSONObject] = []
    primary_endpoints: JSONObject = {}
    for shard in shard_paths:
        manifest = _read_json(shard / "manifest.json")
        results = _read_json(shard / "results.json")
        if manifest.get("dataset_id") != base_manifest.get("dataset_id"):
            raise ValueError(f"dataset mismatch in shard: {shard}")
        shard_input_spec = _object(manifest.get("input"), "input")
        shard_input_manifest_path = _safe_run_path(
            shard, shard_input_spec.get("manifest"), "input.manifest"
        )
        if _read_json(shard_input_manifest_path) != base_input_manifest:
            raise ValueError(f"input manifest mismatch in shard: {shard}")
        shard_source = _safe_run_path(shard, "input/source.csv", "input/source.csv")
        if _sha256(shard_source) != base_source_sha256:
            raise ValueError(f"input source mismatch in shard: {shard}")
        if _format_identities(shard, manifest) != base_formats:
            raise ValueError(f"format artifact identity mismatch in shard: {shard}")
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
        terminal_formats = {
            name
            for name, identity in base_formats.items()
            if identity.get("state")
            in {ExecutionState.UNSUPPORTED, ExecutionState.FAILED}
        }
        if any(
            any(job_id.startswith(f"{name}/") for name in terminal_formats)
            for job_id in _object_map(results.get("results", {}), f"{shard}/results")
        ):
            raise ValueError(f"terminal format has benchmark job: {shard}")
        if results.get("profile") != "equivalence":
            raise ValueError(f"shard does not declare the equivalence profile: {shard}")
        equivalence = _object(results.get("equivalence"), f"{shard}/equivalence")
        equivalence_contracts.append(
            {
                "contract_version": equivalence.get("contract_version", "1"),
                "bounds": _object(
                    equivalence.get("bounds", {}), f"{shard}/equivalence.bounds"
                ),
                "multiplicity_control": _object(
                    equivalence.get("multiplicity_control", {}),
                    f"{shard}/equivalence.multiplicity_control",
                ),
            }
        )
        for pair, endpoint in _object_map(
            equivalence.get("primary_endpoints", {}),
            f"{shard}/equivalence.primary_endpoints",
        ).items():
            if pair in primary_endpoints and primary_endpoints[pair] != endpoint:
                raise ValueError(f"conflicting primary endpoint: {pair}")
            primary_endpoints[pair] = endpoint
        pairs = _object_map(
            equivalence.get("pairs"), f"{shard}/equivalence.pairs"
        )
        if not pairs:
            raise ValueError(f"shard has no equivalence pair evidence: {shard}")
        for job_id, evidence in _object_map(
            results.get("results", {}), f"{shard}/results"
        ).items():
            if job_id in merged_results:
                previous = _object(merged_results[job_id], f"{shard}/results/{job_id}")
                if {
                    key: previous.get(key) for key in ("status", "result", "evidence")
                } != {
                    key: evidence.get(key) for key in ("status", "result", "evidence")
                }:
                    raise ValueError(f"conflicting shared benchmark job: {job_id}")
                shared_job_ids.append(job_id)
                continue
            merged_results[job_id] = evidence
        for pair, evidence in pairs.items():
            if pair in merged_pairs:
                raise ValueError(f"duplicate equivalence pair: {pair}")
            merged_pairs[pair] = evidence
        environments.append(_object(results["environment"], f"{shard}/environment"))
        measurements.append(_object(results["measurement"], f"{shard}/measurement"))
        shard_records.append(
            {
                "path": str(shard.relative_to(shard_root)),
                "state": results["state"],
            }
        )

    if len({strict_json_dumps(value, sort_keys=True) for value in environments}) != 1:
        raise ValueError("shard environments do not match")
    if len({strict_json_dumps(value, sort_keys=True) for value in measurements}) != 1:
        raise ValueError("shard measurement protocols do not match")
    if (
        len(
            {
                strict_json_dumps(value, sort_keys=True)
                for value in equivalence_contracts
            }
        )
        != 1
    ):
        raise ValueError("shard equivalence contracts do not match")
    _copy_run_files(base_run, output_run)

    manifest = dict(base_manifest)
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    manifest["state"] = transition(
        ExecutionState.ROUNDTRIP_VERIFIED, ExecutionState.BENCHMARKED
    )
    first_shard_results = _read_json(shard_paths[0] / "results.json")
    equivalence_value: JSONObject = {
        **equivalence_contracts[0],
        "primary_endpoints": primary_endpoints,
        "parallel_jobs": True,
        "shard_count": len(shard_paths),
        "shared_job_ids": shared_job_ids,
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
    combined["shared_job_ids"] = shared_job_ids
    combined["shards"] = shard_records
    _write_json(output_run / "results.json", combined)
    return output_run / "results.json"
