from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Callable,
    Protocol,
    TypeVar,
)

import pyarrow as pa
import zstandard as zstd

from format_bench.adapter_contract import AdapterManifest, VerificationResult
from format_bench.model import Comparability, Lane

if TYPE_CHECKING:
    from format_bench.fair import Operation

T = TypeVar("T")


class ParserRejection(Exception):
    """A native parser rejected the supplied artifact."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


def parse_artifact(reader: Callable[[], T], errors: tuple[type[Exception], ...]) -> T:
    # LLM contract: PARSER_CALLED -> PARSED | PARSER_REJECTED.
    try:
        return reader()
    except errors as error:
        if isinstance(error, OSError) and (
            type(error) is not OSError or error.errno is not None
        ):
            raise
        raise ParserRejection(error) from error


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
    # LLM contract: MANIFEST_VALIDATED -> ADAPTER_CALLED ->
    # ROUNDTRIP_VERIFIED | FAILED.
    def describe(self) -> FormatDescription: ...

    def encode(self, table: pa.Table, path: Path) -> Artifact: ...

    def read(self, path: Path, manifest: AdapterManifest) -> pa.Table: ...

    def verify_roundtrip(
        self,
        path: Path,
        manifest: AdapterManifest,
    ) -> VerificationResult: ...

    def scan(
        self,
        path: Path,
        manifest: AdapterManifest,
        operation: Operation,
    ) -> pa.Table: ...


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
