from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TypeGuard

import pyarrow as pa

from .formats.arrow_ipc import ArrowIpcAdapter
from .json_contract import strict_json_dumps
from .runner import environment_info


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _null_positions(table: pa.Table) -> dict[str, list[int]]:
    return {
        name: [index for index, value in enumerate(table[name].to_pylist()) if value is None]
        for name in table.column_names
    }


def _is_evidence_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _failure_evidence(error_type: str, error: str) -> dict[str, object]:
    return {"status": "FAILED", "error_type": error_type, "error": error}


def _consume(
    path: Path,
    manifest: dict,
    expected_null_positions: dict[str, list[int]],
) -> dict[str, object]:
    manifest_path = path.parent / "manifest.json"
    manifest_path.write_text(strict_json_dumps(manifest, sort_keys=True), encoding="utf-8")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "format_bench.interop_worker",
            "--artifact",
            str(path),
            "--manifest",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        result: object = json.loads(process.stdout)
    except json.JSONDecodeError:
        return _failure_evidence(
            "WorkerProtocolError", process.stderr[-500:] or "worker did not return JSON"
        )
    if not _is_evidence_object(result):
        return _failure_evidence(
            "WorkerProtocolError", "worker returned a non-object JSON value"
        )
    if process.returncode != 0:
        result["status"] = "FAILED"
        result.setdefault("error", process.stderr[-500:])
    if result.get("status") == "PASS" and (
        result.get("canonical_hash") != manifest["canonical_hash"]
        or result.get("expected_counts") != manifest["expected_counts"]
        or result.get("null_positions") != expected_null_positions
    ):
        result = _failure_evidence(
            "ContractMismatch", "worker returned values outside the canonical contract"
        )
    return result


def _markdown(evidence: dict) -> str:
    lines = [
        "# Arrow IPC independent-consumer interoperability",
        "",
        "This evidence uses a child process that opens Arrow IPC directly with PyArrow.",
        "It does not call `ArrowIpcAdapter.read()` or `verify_roundtrip()`.",
        "The result is limited to this consumer boundary; it is not a cross-language matrix.",
        "",
        "| Variant | Status | Artifact SHA-256 | Decode ms |",
        "| --- | --- | --- | --- |",
    ]
    for item in evidence["variants"]:
        lines.append(
            f"| {item['format']} | {item['status']} | {item['artifact_sha256']} | "
            f"{item.get('decode_ms', 'N/A')} |"
        )
    lines.extend(["", "## Invalid-artifact controls", "", "| Case | Status | Error |", "| --- | --- | --- |"])
    for item in evidence["negative_cases"]:
        lines.append(f"| {item['case']} | {item['status']} | {item.get('error', 'N/A')} |")
    return "\n".join(lines) + "\n"


def run_arrow_ipc_interoperability(
    table: pa.Table,
    manifest: dict,
    output: Path,
    *,
    environment: dict | None = None,
) -> Path:
    if output.exists():
        raise FileExistsError(f"interoperability output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    expected_null_positions = _null_positions(table)
    try:
        variants = []
        for compression in ("none", "lz4", "zstd"):
            adapter = ArrowIpcAdapter(compression)
            artifact = stage / f"{adapter.name}.arrow"
            try:
                # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED;
                # this lane writes ENCODED and advances to ROUNDTRIP_VERIFIED only on consumer PASS.
                adapter.encode(table, artifact)
                result = _consume(artifact, manifest, expected_null_positions)
            except (ImportError, ModuleNotFoundError) as error:
                result = _failure_evidence(type(error).__name__, str(error))
                result["status"] = "UNSUPPORTED"
            except Exception as error:
                result = _failure_evidence(type(error).__name__, str(error))
            result.update(
                {
                    "format": adapter.name,
                    "compression": compression,
                    "artifact_sha256": _sha256(artifact) if artifact.is_file() else None,
                }
            )
            variants.append(result)

        source_path = stage / "arrow_ipc.arrow"
        negative_cases = []
        if source_path.is_file():
            source = source_path.read_bytes()
            negative_inputs = (
                ("truncated", source[: len(source) // 2]),
                ("invalid", b"not-arrow-ipc\n"),
            )
            for case, data in negative_inputs:
                artifact = stage / f"{case}.arrow"
                artifact.write_bytes(data)
                result = _consume(artifact, manifest, expected_null_positions)
                result.update({"case": case, "artifact_sha256": _sha256(artifact)})
                negative_cases.append(result)
        else:
            negative_cases = [
                {
                    "case": case,
                    "status": "FAILED",
                    "error_type": "BaseArtifactUnavailable",
                    "error": "arrow_ipc artifact was not produced",
                    "artifact_sha256": None,
                }
                for case in ("truncated", "invalid")
            ]

        evidence = {
            "schema_version": "1",
            "contract_version": "1",
            "consumer": {
                "entrypoint": "format_bench.interop_worker",
                "python": sys.version.split()[0],
                "pyarrow": pa.__version__,
            },
            "environment": environment or environment_info(Path.cwd()),
            "canonical_hash": manifest["canonical_hash"],
            "expected_counts": manifest["expected_counts"],
            "expected_null_positions": expected_null_positions,
            "variants": variants,
            "negative_cases": negative_cases,
        }
        evidence_path = stage / "arrow-ipc-interoperability.json"
        evidence_path.write_text(
            strict_json_dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / "arrow-ipc-interoperability.md").write_text(
            _markdown(evidence), encoding="utf-8"
        )
        if output.exists():
            raise FileExistsError(f"interoperability output already exists: {output}")
        os.replace(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return output / "arrow-ipc-interoperability.json"
