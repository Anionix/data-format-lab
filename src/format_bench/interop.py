from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pyarrow as pa

from .formats.arrow_ipc import ArrowIpcAdapter
from .runner import environment_info


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _consume(path: Path, manifest: dict) -> dict:
    manifest_path = path.parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
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
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {
            "status": "FAILED",
            "error_type": "WorkerProtocolError",
            "error": process.stderr[-500:] or "worker did not return JSON",
        }
    if not isinstance(result, dict):
        return {
            "status": "FAILED",
            "error_type": "WorkerProtocolError",
            "error": "worker returned a non-object JSON value",
        }
    if process.returncode != 0:
        result["status"] = "FAILED"
        result.setdefault("error", process.stderr[-500:])
    if result.get("status") == "PASS" and (
        result.get("canonical_hash") != manifest["canonical_hash"]
        or result.get("expected_counts") != manifest["expected_counts"]
    ):
        result = {
            "status": "FAILED",
            "error_type": "ContractMismatch",
            "error": "worker returned values outside the canonical contract",
        }
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
    output.mkdir(parents=True, exist_ok=True)
    variants = []
    for compression in ("none", "lz4", "zstd"):
        adapter = ArrowIpcAdapter(compression)
        artifact = output / f"{adapter.name}.arrow"
        adapter.encode(table, artifact)
        result = _consume(artifact, manifest)
        result.update(
            {
                "format": adapter.name,
                "compression": compression,
                "artifact_sha256": _sha256(artifact),
            }
        )
        variants.append(result)

    source = (output / "arrow_ipc.arrow").read_bytes()
    negative_cases = []
    for case, data in (("truncated", source[: len(source) // 2]), ("invalid", b"not-arrow-ipc\n")):
        artifact = output / f"{case}.arrow"
        artifact.write_bytes(data)
        result = _consume(artifact, manifest)
        result.update({"case": case, "artifact_sha256": _sha256(artifact)})
        negative_cases.append(result)

    evidence = {
        "schema_version": "1",
        "contract_version": "1",
        "consumer": {
            "entrypoint": "format_bench.interop_worker",
            "python": sys.version.split()[0],
            "pyarrow": pa.__version__,
        },
        "environment": environment
        or environment_info(Path.cwd()),
        "canonical_hash": manifest["canonical_hash"],
        "expected_counts": manifest["expected_counts"],
        "variants": variants,
        "negative_cases": negative_cases,
    }
    evidence_path = output / "arrow-ipc-interoperability.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "arrow-ipc-interoperability.md").write_text(
        _markdown(evidence), encoding="utf-8"
    )
    return evidence_path
