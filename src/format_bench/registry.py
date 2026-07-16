from __future__ import annotations

from .formats.base import FormatAdapter
from .formats.arrow_ipc import ArrowIpcAdapter
from .formats.lance import LanceAdapter
from .formats.parquet import ParquetAdapter
from .formats.text import CsvAdapter, ObjectJsonlAdapter
from .formats.tsfile import TsFileAdapter
from .formats.vortex import VortexAdapter


def adapters() -> tuple[FormatAdapter, ...]:
    return (
        CsvAdapter(),
        ObjectJsonlAdapter(),
        ArrowIpcAdapter(),
        ArrowIpcAdapter("lz4"),
        ArrowIpcAdapter("zstd"),
        ParquetAdapter(),
        ParquetAdapter(compression_level=19),
        LanceAdapter(),
        VortexAdapter(),
        VortexAdapter(compact=True),
        TsFileAdapter(),
    )


def adapter_map() -> dict[str, FormatAdapter]:
    registered = {adapter.describe().name: adapter for adapter in adapters()}
    if len(registered) != len(adapters()):
        raise ValueError("format adapter names must be unique")
    return registered
