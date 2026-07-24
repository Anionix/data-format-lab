from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NotRequired, Required, TypedDict, cast

from .json_contract import strict_json_loads
from .model import ExecutionState


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


class VerificationFormat(TypedDict, total=False):
    format: Required[str]
    artifact: Required[str]
    state: Required[ExecutionState]
    size_observations: SizeObservations
    verification: dict[str, object]
    failure_reason: str


class VerificationInput(TypedDict):
    manifest: str


class VerificationManifest(TypedDict, total=False):
    input: Required[VerificationInput]
    formats: Required[list[VerificationFormat]]
    state: Required[ExecutionState]
    failure_reason: str


@dataclass(frozen=True)
class VerificationContract:
    manifest: VerificationManifest
    dataset_manifest: dict[str, object]
    artifact_paths: tuple[Path, ...]


def json_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{label} keys must be strings")
    return cast(dict[str, object], raw)


def _required_text(value: dict[str, object], name: str, label: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{label}.{name} must be a non-empty string")
    return item


def _required_int(value: dict[str, object], name: str, label: str) -> int:
    item = value.get(name)
    if type(item) is not int or item < 0:
        raise ValueError(f"{label}.{name} must be a non-negative integer")
    return item


def _relative_path(
    root: Path,
    value: str,
    label: str,
    *,
    regular_file: bool = False,
    namespace: str | None = None,
) -> Path:
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} must be run-relative")
    candidate = root / relative
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} must be run-relative") from error
    if namespace is not None:
        namespace_root = root / namespace
        if namespace_root.is_symlink():
            raise ValueError(f"{label} must be below {namespace}/")
        try:
            relative_to_namespace = resolved.relative_to(
                namespace_root.resolve(strict=False)
            )
        except ValueError as error:
            raise ValueError(f"{label} must be below {namespace}/") from error
        if not relative_to_namespace.parts:
            raise ValueError(f"{label} must be below {namespace}/")
    if regular_file and (candidate.is_symlink() or not candidate.is_file()):
        raise ValueError(f"{label} must be a regular file")
    return candidate


def _size_observations(value: object, index: int) -> SizeObservations:
    label = f"run manifest formats[{index}].size_observations"
    observations = json_object(value, label)
    if observations.get("contract_version") != "1":
        raise ValueError(f"{label}.contract_version must be 1")
    if observations.get("resampling_unit") != "same_process_encode_invocation":
        raise ValueError(f"{label}.resampling_unit is not recognized")
    attempted = _required_int(observations, "attempted", label)
    completed = _required_int(observations, "completed", label)
    if completed > attempted:
        raise ValueError(f"{label}.completed exceeds attempted")
    raw_attempts = observations.get("attempts")
    if not isinstance(raw_attempts, list) or not raw_attempts:
        raise ValueError(f"{label}.attempts must be a non-empty list")
    attempts: list[SizeAttempt] = []
    for attempt_index, value in enumerate(cast(list[object], raw_attempts)):
        attempt_label = f"{label}.attempts[{attempt_index}]"
        attempt = json_object(value, attempt_label)
        _required_int(attempt, "index", attempt_label)
        if attempt.get("status") not in {"MEASURED", "FAILED"}:
            raise ValueError(f"{attempt_label}.status is not recognized")
        for name in ("native_bytes", "transport_zstd_bytes"):
            item = attempt.get(name)
            if item is not None and (type(item) is not int or item < 0):
                raise ValueError(f"{attempt_label}.{name} must be non-negative")
        digest = attempt.get("artifact_sha256")
        if digest is not None and not isinstance(digest, str):
            raise ValueError(f"{attempt_label}.artifact_sha256 must be a string")
        verified = attempt.get("roundtrip_verified")
        if verified is not None and not isinstance(verified, bool):
            raise ValueError(f"{attempt_label}.roundtrip_verified must be a boolean")
        failure_reason = attempt.get("failure_reason")
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError(f"{attempt_label}.failure_reason must be a string")
        attempts.append(cast(SizeAttempt, attempt))
    observations["attempts"] = attempts
    return cast(SizeObservations, observations)


def _format_entry(value: object, index: int) -> VerificationFormat:
    label = f"run manifest formats[{index}]"
    entry = json_object(value, label)
    _required_text(entry, "format", label)
    _required_text(entry, "artifact", label)
    try:
        entry["state"] = ExecutionState(_required_text(entry, "state", label))
    except ValueError as error:
        raise ValueError(f"{label}.state is not recognized") from error
    if "size_observations" in entry:
        entry["size_observations"] = _size_observations(
            entry["size_observations"], index
        )
    return cast(VerificationFormat, entry)


def load_verification_contract(run_dir: Path) -> VerificationContract:
    manifest_path = run_dir / "manifest.json"
    run_manifest = json_object(
        strict_json_loads(manifest_path.read_text(encoding="utf-8")),
        "run manifest",
    )
    raw_input = json_object(run_manifest.get("input"), "run manifest input")
    input_manifest = _required_text(raw_input, "manifest", "run manifest input")
    raw_formats = run_manifest.get("formats")
    if not isinstance(raw_formats, list):
        raise ValueError("run manifest formats must be a list")
    formats = [
        _format_entry(value, index)
        for index, value in enumerate(cast(list[object], raw_formats))
    ]
    try:
        run_manifest["state"] = ExecutionState(
            _required_text(run_manifest, "state", "run manifest")
        )
    except ValueError as error:
        raise ValueError("run manifest.state is not recognized") from error

    # LLM contract: invalid persistent evidence terminates before adapters run;
    # only validated ENCODED entries may advance to ROUNDTRIP_VERIFIED.
    dataset_path = _relative_path(
        run_dir,
        input_manifest,
        "input manifest",
        regular_file=True,
    )
    dataset_manifest = json_object(
        strict_json_loads(dataset_path.read_text(encoding="utf-8")),
        "dataset manifest",
    )
    artifact_paths = tuple(
        _relative_path(
            run_dir,
            entry["artifact"],
            "artifact path",
            namespace="artifacts",
        )
        for entry in formats
    )
    raw_input["manifest"] = input_manifest
    run_manifest["input"] = cast(VerificationInput, raw_input)
    run_manifest["formats"] = formats
    return VerificationContract(
        manifest=cast(VerificationManifest, run_manifest),
        dataset_manifest=dataset_manifest,
        artifact_paths=artifact_paths,
    )
