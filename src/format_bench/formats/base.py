from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

import pyarrow as pa
import zstandard as zstd

from format_bench.model import Comparability, Lane

if TYPE_CHECKING:
    from format_bench.fair import FairOperation


@dataclass(frozen=True)
class FormatDescription:
    name: str
    lane: Lane
    comparability: Comparability
    extension: str
    settings: dict[str, object]


@dataclass(frozen=True)
class Artifact:
    path: Path
    native_bytes: int
    transport_zstd_bytes: int
    prepare_write_ms: float


class FormatAdapter(Protocol):
    def describe(self) -> FormatDescription: ...

    def encode(self, table: pa.Table, path: Path) -> Artifact: ...

    def read(self, path: Path, manifest: dict) -> pa.Table: ...

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict: ...

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table: ...


def write_artifact(path: Path, writer: Callable[[], None]) -> Artifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter_ns()
    writer()
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    data = path.read_bytes()
    return Artifact(
        path=path,
        native_bytes=len(data),
        transport_zstd_bytes=len(zstd.ZstdCompressor(level=3).compress(data)),
        prepare_write_ms=round(elapsed_ms, 3),
    )
