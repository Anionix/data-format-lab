from __future__ import annotations

from .formats.base import FormatAdapter
from .formats.arrow_extra import FeatherV2Adapter, OrcAdapter
from .formats.arrow_ipc import ArrowIpcAdapter
from .formats.database import DuckDbAdapter, SqliteAdapter
from .formats.lance import LanceAdapter
from .formats.parquet import ParquetAdapter
from .formats.row import AvroAdapter, CborAdapter, MessagePackAdapter
from .formats.text import CsvAdapter, ObjectJsonlAdapter, TsvAdapter
from .formats.tsfile import TsFileAdapter
from .formats.vortex import VortexAdapter


def adapters() -> tuple[FormatAdapter, ...]:
    return (
        CsvAdapter(),
        TsvAdapter(),
        ObjectJsonlAdapter(),
        ArrowIpcAdapter(),
        ArrowIpcAdapter("lz4"),
        ArrowIpcAdapter("zstd"),
        FeatherV2Adapter(),
        OrcAdapter(),
        ParquetAdapter(),
        ParquetAdapter(compression_level=19),
        ParquetAdapter(compression="snappy"),
        ParquetAdapter(compression="gzip"),
        LanceAdapter(),
        VortexAdapter(),
        VortexAdapter(compact=True),
        TsFileAdapter(),
        AvroAdapter(),
        MessagePackAdapter(),
        CborAdapter(),
        SqliteAdapter(),
        DuckDbAdapter(),
    )


def adapter_map() -> dict[str, FormatAdapter]:
    registered = {adapter.describe().name: adapter for adapter in adapters()}
    if len(registered) != len(adapters()):
        raise ValueError("format adapter names must be unique")
    return registered
