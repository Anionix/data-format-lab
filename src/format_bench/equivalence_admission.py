from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .artifact_digest import artifact_sha256


def expected_size_observations(fixture: bool) -> int:
    return 2 if fixture else 10


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_artifact_path(run_dir: Path, value: object, name: object) -> Path:
    if not isinstance(value, str) or "\x00" in value or "\\" in value:
        raise ValueError(f"invalid canonical artifact path for {name}")
    relative = Path(value)
    if (
        relative.is_absolute()
        or len(relative.parts) != 2
        or relative.parts[0] != "artifacts"
        or relative.parts[1] in {"", ".", ".."}
        or relative.as_posix() != value
    ):
        raise ValueError(f"invalid canonical artifact path for {name}")
    candidate = run_dir / relative
    try:
        candidate.parent.resolve(strict=True).relative_to(run_dir.resolve(strict=True))
    except (FileNotFoundError, ValueError) as error:
        raise ValueError(f"invalid canonical artifact path for {name}") from error
    return candidate


def _validate_entry(run_dir: Path, entry: dict, expected: int) -> None:
    name = entry.get("format", "unknown")
    evidence = entry.get("size_observations")
    if not isinstance(evidence, dict):
        raise ValueError(
            f"equivalence run needs repeated size observations for {name}; "
            f"prepare with --size-observations {expected}"
        )
    attempts = evidence.get("attempts")
    if (
        evidence.get("contract_version") != "1"
        or evidence.get("resampling_unit") != "same_process_encode_invocation"
        or not isinstance(attempts, list)
        or evidence.get("attempted") != evidence.get("completed")
        or evidence.get("completed") != len(attempts)
        or len(attempts) != expected
    ):
        raise ValueError(
            f"equivalence run needs exactly {expected} repeated size observations "
            f"for {name}; prepare with --size-observations {expected}"
        )

    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict):
            raise ValueError(f"invalid size observation {index} for {name}")
        sizes = (attempt.get("native_bytes"), attempt.get("transport_zstd_bytes"))
        if (
            attempt.get("index") != index
            or attempt.get("status") != "MEASURED"
            or attempt.get("roundtrip_verified") is not True
            or not _is_sha256(attempt.get("artifact_sha256"))
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in sizes
            )
        ):
            raise ValueError(
                f"invalid size observation {index} for {name}; "
                f"prepare with --size-observations {expected}"
            )

    artifact = entry.get("artifact")
    artifact_path = _canonical_artifact_path(run_dir, artifact, name)
    try:
        actual_digest = artifact_sha256(artifact_path)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot verify canonical artifact for {name}") from error
    if attempts[0]["artifact_sha256"] != actual_digest:
        raise ValueError(f"observation-zero artifact digest is stale for {name}")


def validate_equivalence_admission(
    run_dir: Path, manifest: dict, format_names: Iterable[str]
) -> None:
    """Validate rankable size evidence before equivalence measurement starts."""
    fixture = manifest.get("fixture")
    if not isinstance(fixture, bool):
        raise ValueError("equivalence run fixture flag must be boolean")
    expected = expected_size_observations(fixture)
    formats = {
        entry.get("format"): entry
        for entry in manifest.get("formats", ())
        if isinstance(entry, dict)
    }
    # LLM contract: ROUNDTRIP_VERIFIED evidence may enter BENCHMARKED only
    # after admission passes; rejection preserves the pre-benchmark manifest.
    for name in sorted(set(format_names)):
        entry = formats.get(name)
        if isinstance(entry, dict):
            _validate_entry(run_dir, entry, expected)
