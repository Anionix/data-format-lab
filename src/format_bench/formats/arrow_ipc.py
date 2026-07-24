from __future__ import annotations

from typing import Literal
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

from format_bench.adapter_contract import AdapterManifest
from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import Operation, apply_arrow
from format_bench.model import Comparability, Lane

from .base import Artifact, FormatDescription, VerificationResult, write_artifact

ArrowIpcCompression = Literal["none", "lz4", "zstd"]


class ArrowIpcAdapter:
    """Arrow IPC file container with the same canonical contract as fair formats."""

    def __init__(self, compression: ArrowIpcCompression = "none") -> None:
        if compression not in {"none", "lz4", "zstd"}:
            raise ValueError(f"unsupported Arrow IPC compression: {compression}")
        self.compression = compression
        self.name = "arrow_ipc" if compression == "none" else f"arrow_ipc_{compression}"

    def describe(self) -> FormatDescription:
        return FormatDescription(
            name=self.name,
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".arrow",
            settings={"container": "arrow-ipc-file", "compression": self.compression},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            with pa.OSFile(str(path), "wb") as sink:
                options = ipc.IpcWriteOptions(
                    compression=None if self.compression == "none" else self.compression
                )
                with ipc.new_file(sink, table.schema, options=options) as writer:
                    writer.write_table(table)

        return write_artifact(path, write)

    def read(self, path: Path, manifest: AdapterManifest) -> pa.Table:
        schema = arrow_schema(manifest)
        with pa.memory_map(str(path), "r") as source:
            table = ipc.open_file(source).read_all()
        return table.select(schema.names)

    def verify_roundtrip(
        self, path: Path, manifest: AdapterManifest
    ) -> VerificationResult:
        return verify_table(self.read(path, manifest), manifest)

    def scan(
        self, path: Path, manifest: AdapterManifest, operation: Operation
    ) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation, manifest)
