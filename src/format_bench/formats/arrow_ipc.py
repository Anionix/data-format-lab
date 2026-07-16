from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import FairOperation, apply_arrow
from format_bench.model import Comparability, Lane

from .base import Artifact, FormatDescription, write_artifact


class ArrowIpcAdapter:
    """Arrow IPC file container with the same canonical contract as fair formats."""

    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="arrow_ipc",
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".arrow",
            settings={"container": "arrow-ipc-file", "compression": "none"},
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            with pa.OSFile(str(path), "wb") as sink:
                with ipc.new_file(sink, table.schema) as writer:
                    writer.write_table(table)

        return write_artifact(path, write)

    def read(self, path: Path, manifest: dict) -> pa.Table:
        schema = arrow_schema(manifest)
        with pa.memory_map(str(path), "r") as source:
            table = ipc.open_file(source).read_all()
        return table.select(schema.names)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        return apply_arrow(self.read(path, manifest), operation)
