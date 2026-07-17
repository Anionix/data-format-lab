from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import vortex

from format_bench.canonical import arrow_schema, verify_table
from format_bench.fair import FairOperation, arrow_filter, columns_for, limit_for
from format_bench.model import Comparability, Lane

from .base import Artifact, FormatDescription, write_artifact


class VortexAdapter:
    def __init__(self, compact: bool = False) -> None:
        self.compact = compact

    def describe(self) -> FormatDescription:
        return FormatDescription(
            name="vortex_compact" if self.compact else "vortex_default",
            lane=Lane.FAIR,
            comparability=Comparability.FULL_COMPARABLE,
            extension=".vortex",
            settings={
                "writer": "compact" if self.compact else "default",
                "batch_rows": 4096 if self.compact else None,
            },
        )

    def encode(self, table: pa.Table, path: Path) -> Artifact:
        def write() -> None:
            if self.compact:
                batches = table.to_batches(max_chunksize=4096)
                reader = pa.RecordBatchReader.from_batches(table.schema, batches)
                vortex.io.VortexWriteOptions.compact().write(reader, str(path))
            else:
                vortex.io.write(table, str(path))

        return write_artifact(path, write)

    def read(self, path: Path, manifest: dict) -> pa.Table:
        schema = arrow_schema(manifest)
        table = vortex.open(str(path)).to_dataset().to_table().select(schema.names)
        return table if table.schema == schema else table.cast(schema)

    def verify_roundtrip(self, path: Path, manifest: dict) -> dict:
        return verify_table(self.read(path, manifest), manifest)

    def scan(self, path: Path, manifest: dict, operation: FairOperation) -> pa.Table:
        dataset = vortex.open(str(path)).to_dataset()
        limit = limit_for(operation, manifest["rows"], manifest)
        columns = columns_for(operation, manifest)
        kwargs = {"columns": columns, "filter": arrow_filter(operation, manifest)}
        table = dataset.head(limit, **kwargs) if limit is not None else dataset.to_table(**kwargs)
        schema = arrow_schema(manifest)
        if columns:
            schema = pa.schema(schema.field(name) for name in columns)
        return table if table.schema == schema else table.cast(schema)
