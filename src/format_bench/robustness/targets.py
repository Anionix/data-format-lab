from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard as zstd

from format_bench.canonical import arrow_schema
from format_bench.formats.base import Artifact, FormatAdapter
from format_bench.model import TargetTier
from format_bench.registry import adapter_map


@dataclass(frozen=True)
class RobustnessTarget:
    name: str
    adapter: FormatAdapter
    tier: TargetTier = TargetTier.CORE


def core_targets() -> tuple[RobustnessTarget, ...]:
    registered = adapter_map()
    return tuple(
        RobustnessTarget(name, registered[name])
        for name in ("csv", "object_jsonl", "parquet_default", "parquet_zstd19")
    )


def target_map() -> dict[str, RobustnessTarget]:
    return {target.name: target for target in core_targets()}


def read_robustness(target: RobustnessTarget, path: Path, manifest: dict) -> pa.Table:
    expected = arrow_schema(manifest).names
    if target.name == "object_jsonl":
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            value = json.loads(line)
            if not isinstance(value, dict) or set(value) != set(expected):
                raise ValueError(f"JSONL object shape mismatch at line {line_number}")
    elif target.name.startswith("parquet_"):
        physical = pq.ParquetFile(path).schema_arrow.names
        if physical != expected:
            raise ValueError(f"Parquet schema mismatch: expected {expected}, got {physical}")
    return target.adapter.read(path, manifest)


def encode_valid(target: RobustnessTarget, table: pa.Table, path: Path) -> Artifact:
    return target.adapter.encode(table, path)


def _text_malformed(data: bytes, target: str, kind: str) -> bytes:
    if target == "csv":
        lines = data.decode("utf-8").splitlines(keepends=True)
        if not lines:
            return data
        if kind == "missing_column":
            newline = "\n" if lines[0].endswith("\n") else ""
            return (lines[0].rstrip("\r\n").rsplit(",", 1)[0] + newline + "".join(lines[1:])).encode()
        if kind == "extra_column" and len(lines) > 1:
            line = lines[1].rstrip("\r\n") + ",unexpected\n"
            return lines[0].encode() + line.encode() + b"".join(item.encode() for item in lines[2:])
    if target == "object_jsonl":
        lines = data.decode("utf-8").splitlines(keepends=True)
        if lines:
            row = json.loads(lines[0])
            if kind == "missing_column":
                row.pop("description", None)
            elif kind == "extra_column":
                row["unexpected"] = "x"
            lines[0] = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            return "".join(lines).encode("utf-8")
    raise ValueError(f"unsupported text target or malformed case: {target}/{kind}")


def encode_malformed(target: RobustnessTarget, table: pa.Table, path: Path, kind: str) -> Artifact:
    if target.name in {"csv", "object_jsonl"}:
        artifact = target.adapter.encode(table, path)
        path.write_bytes(_text_malformed(path.read_bytes(), target.name, kind))
        data = path.read_bytes()
        return replace(
            artifact,
            native_bytes=len(data),
            transport_zstd_bytes=len(zstd.ZstdCompressor(level=3).compress(data)),
        )
    if kind == "missing_column":
        malformed = table.drop([table.column_names[-1]])
    elif kind == "extra_column":
        malformed = table.append_column("unexpected", pa.array(["x"] * table.num_rows, type=pa.string()))
    else:
        raise ValueError(f"unsupported column case: {kind}")
    return target.adapter.encode(malformed, path)
