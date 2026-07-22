from __future__ import annotations

import csv
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import lance
import vortex
import zstandard as zstd

from format_bench.canonical import arrow_schema
from format_bench.formats.base import (
    Artifact,
    FormatAdapter,
    ParserRejection,
    parse_artifact,
)
from format_bench.model import TargetTier
from format_bench.registry import adapter_map


class TargetExecutionError(Exception):
    """An exception raised by the format target at the adapter boundary."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


@dataclass(frozen=True)
class RobustnessTarget:
    name: str
    adapter: FormatAdapter
    tier: TargetTier = TargetTier.CORE


def core_targets() -> tuple[RobustnessTarget, ...]:
    registered = adapter_map()
    return tuple(
        RobustnessTarget(name, registered[name])
        for name in (
            "csv",
            "object_jsonl",
            "parquet_default",
            "parquet_zstd19",
            "lance_base",
            "vortex_default",
            "vortex_compact",
        )
    )


def target_map() -> dict[str, RobustnessTarget]:
    return {target.name: target for target in core_targets()}


def read_target(adapter: FormatAdapter, path: Path, manifest: dict) -> pa.Table:
    # Adapter exceptions remain harness failures unless the adapter explicitly
    # raises TargetExecutionError at a target boundary.
    return adapter.read(path, manifest)


def _csv_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle), [])


def read_robustness(target: RobustnessTarget, path: Path, manifest: dict) -> pa.Table:
    schema = arrow_schema(manifest)
    expected = schema.names
    # LLM contract: PARSER_RAISED -> TARGET_REJECTED; undeclared errors -> HARNESS_FAILED.
    try:
        if target.name == "csv":
            physical = parse_artifact(
                lambda: _csv_header(path), (csv.Error, OSError, UnicodeError)
            )
            if physical != expected:
                raise TargetExecutionError(
                    ValueError(f"CSV header mismatch: expected {expected}, got {physical}")
                )
        elif target.name == "object_jsonl":
            lines = parse_artifact(
                lambda: path.read_text(encoding="utf-8").splitlines(),
                (OSError, UnicodeError),
            )
            for line_number, line in enumerate(lines, 1):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise TargetExecutionError(error) from error
                if not isinstance(value, dict) or set(value) != set(expected):
                    raise TargetExecutionError(
                        ValueError(f"JSONL object shape mismatch at line {line_number}")
                    )
        elif target.name.startswith("parquet_"):
            physical = parse_artifact(
                lambda: pq.ParquetFile(path).schema_arrow.names,
                (pa.ArrowException, OSError, ValueError),
            )
            if physical != expected:
                raise TargetExecutionError(
                    ValueError(f"Parquet schema mismatch: expected {expected}, got {physical}")
                )
        elif target.name == "lance_base":
            physical = parse_artifact(
                lambda: lance.dataset(path).schema.names,
                (pa.ArrowException, OSError, RuntimeError, ValueError),
            )
            if physical != expected:
                raise TargetExecutionError(
                    ValueError(f"Lance schema mismatch: expected {expected}, got {physical}")
                )
        elif target.name.startswith("vortex_"):
            physical = parse_artifact(
                lambda: vortex.open(str(path)).to_dataset().schema.names,
                (pa.ArrowException, OSError, RuntimeError, ValueError),
            )
            if physical != expected:
                raise TargetExecutionError(
                    ValueError(f"Vortex schema mismatch: expected {expected}, got {physical}")
                )
        return read_target(target.adapter, path, manifest)
    except TargetExecutionError:
        raise
    except ParserRejection as error:
        raise TargetExecutionError(error.cause) from error


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
            def append_column(line: str) -> str:
                newline = "\n" if line.endswith("\n") else ""
                return line.rstrip("\r\n") + ",unexpected" + newline

            return "".join(append_column(line) for line in lines).encode()
    if target == "object_jsonl":
        if kind not in {"missing_column", "extra_column"}:
            raise ValueError(f"unsupported text target or malformed case: {target}/{kind}")
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
