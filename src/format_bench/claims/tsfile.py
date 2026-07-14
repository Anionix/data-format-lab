from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import pyarrow as pa
import pyarrow.parquet as pq

from format_bench.runner import stats_ms


TABLE_NAME = "sensors"


def _measure(function: Callable[[], int], warmups: int, iterations: int) -> dict:
    for _ in range(warmups):
        function()
    samples, result = [], 0
    for _ in range(iterations):
        started = time.perf_counter_ns()
        result = function()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return {"timing": stats_ms(samples), "result": result}


def _schema() -> tuple[Any, list[str], list[Any]]:
    from tsfile import ColumnCategory, ColumnSchema, TableSchema, TSDataType

    names = ["device", "site", "temperature", "pressure", "active", "sequence"]
    types = [
        TSDataType.STRING,
        TSDataType.STRING,
        TSDataType.DOUBLE,
        TSDataType.DOUBLE,
        TSDataType.BOOLEAN,
        TSDataType.INT64,
    ]
    categories = [
        ColumnCategory.TAG,
        ColumnCategory.TAG,
        ColumnCategory.FIELD,
        ColumnCategory.FIELD,
        ColumnCategory.FIELD,
        ColumnCategory.FIELD,
    ]
    return (
        TableSchema(
            TABLE_NAME,
            columns=[
                ColumnSchema(name, data_type, category)
                for name, data_type, category in zip(names, types, categories, strict=True)
            ],
        ),
        names,
        types,
    )


def _device_table(device_index: int, points: int) -> pa.Table:
    timestamps = list(range(points))
    return pa.table(
        {
            "timestamp": pa.array(timestamps, type=pa.int64()),
            "device": pa.array([f"device-{device_index:03d}"] * points),
            "site": pa.array([f"site-{device_index % 10:02d}"] * points),
            "temperature": pa.array(
                [20.0 + (device_index % 5) + (value % 100) / 100.0 for value in timestamps],
                type=pa.float64(),
            ),
            "pressure": pa.array(
                [1000.0 + (value % 200) / 10.0 for value in timestamps], type=pa.float64()
            ),
            "active": pa.array([value % 2 == 0 for value in timestamps]),
            "sequence": pa.array(
                [device_index * points + value for value in timestamps], type=pa.int64()
            ),
        }
    )


def _configure_tsfile(schema: Any, directory: Path) -> dict[str, Any]:
    from tsfile import (
        Compressor,
        TSDataType,
        TSEncoding,
        TsFileTableWriter,
        get_tsfile_config,
        set_tsfile_config,
    )

    if get_tsfile_config()["page_writer_max_point_num_"] == 0:
        bootstrap = directory / ".tsfile-config-init"
        with TsFileTableWriter(str(bootstrap), schema):
            pass
        bootstrap.unlink()
    settings = {
        "tsblock_mem_inc_step_size_": 8000,
        "tsblock_max_memory_": 64000,
        "page_writer_max_point_num_": 10000,
        "page_writer_max_memory_bytes_": 131072,
        "max_degree_of_index_node_": 256,
        "tsfile_index_bloom_filter_error_percent_": 0.05,
        "time_encoding_type_": TSEncoding.TS_2DIFF,
        "time_data_type_": TSDataType.INT64,
        "time_compress_type_": Compressor.LZ4,
        "chunk_group_size_threshold_": 134217728,
        "record_count_for_next_mem_check_": 100,
        "encrypt_flag_": False,
        "boolean_encoding_type_": TSEncoding.PLAIN,
        "int32_encoding_type_": TSEncoding.TS_2DIFF,
        "int64_encoding_type_": TSEncoding.TS_2DIFF,
        "float_encoding_type_": TSEncoding.GORILLA,
        "double_encoding_type_": TSEncoding.GORILLA,
        "string_encoding_type_": TSEncoding.PLAIN,
        "default_compression_type_": Compressor.LZ4,
    }
    set_tsfile_config(settings)
    actual = get_tsfile_config()
    if any(actual[key] != value for key, value in settings.items()):
        raise ValueError("TsFile writer configuration did not apply")
    return {key: getattr(value, "name", value) for key, value in actual.items()}


def _write_datasets(
    tsfile_path: Path, parquet_path: Path, devices: int, points: int
) -> tuple[dict[str, float], dict[str, Any]]:
    from tsfile import Tablet, TsFileTableWriter

    schema, names, types = _schema()
    tsfile_settings = _configure_tsfile(schema, tsfile_path.parent)
    started = time.perf_counter_ns()
    with TsFileTableWriter(str(tsfile_path), schema) as writer:
        for device_index in range(devices):
            rows = _device_table(device_index, points).to_pylist()
            tablet = Tablet(names, types, points)
            for index, row in enumerate(rows):
                tablet.add_timestamp(index, row["timestamp"])
                for name in names:
                    tablet.add_value_by_name(name, index, row[name])
            writer.write_table(tablet)
    tsfile_ms = (time.perf_counter_ns() - started) / 1_000_000

    started = time.perf_counter_ns()
    parquet = None
    try:
        for device_index in range(devices):
            table = _device_table(device_index, points)
            parquet = parquet or pq.ParquetWriter(parquet_path, table.schema, compression="zstd")
            parquet.write_table(table, row_group_size=points)
    finally:
        if parquet:
            parquet.close()
    return (
        {
            "tsfile": round(tsfile_ms, 3),
            "parquet": round((time.perf_counter_ns() - started) / 1_000_000, 3),
        },
        tsfile_settings,
    )


def run_tsfile_claim(
    directory: Path,
    *,
    devices: int = 100,
    points_per_device: int = 10_000,
    warmups: int = 3,
    iterations: int = 10,
) -> dict:
    from tsfile import TsFileReader, tag_eq

    directory.mkdir(parents=True, exist_ok=True)
    tsfile_path, parquet_path = directory / "sensors.tsfile", directory / "sensors.parquet"
    writes, tsfile_settings = _write_datasets(
        tsfile_path, parquet_path, devices, points_per_device
    )
    columns = ["device", "site", "temperature", "pressure", "active", "sequence"]
    device_index = min(42, devices - 1)
    start = points_per_device // 2
    end = min(points_per_device, start + max(1, points_per_device // 10))
    device = f"device-{device_index:03d}"

    def ts_query() -> int:
        rows = 0
        with TsFileReader(str(tsfile_path)) as reader:
            with reader.query_table(
                TABLE_NAME, columns, start, end - 1, tag_eq("device", device)
            ) as result:
                while result.next():
                    rows += 1
        return rows

    def parquet_query() -> int:
        return pq.read_table(
            parquet_path,
            columns=columns,
            filters=[("device", "=", device), ("timestamp", ">=", start), ("timestamp", "<", end)],
        ).num_rows

    ts_result = _measure(ts_query, warmups, iterations)
    parquet_result = _measure(parquet_query, warmups, iterations)
    status = "MEASURED" if ts_result["result"] == parquet_result["result"] else "FAILED"
    return {
        "status": status,
        "rows": devices * points_per_device,
        "shape": {"devices": devices, "points_per_device": points_per_device},
        "query": f"{device} and timestamp [{start}, {end})",
        "write_ms": writes,
        "writer_settings": {
            "tsfile": tsfile_settings,
            "parquet": {"compression": "zstd", "row_group_size": points_per_device},
        },
        "bytes": {"tsfile": tsfile_path.stat().st_size, "parquet": parquet_path.stat().st_size},
        "timing": {"tsfile": ts_result, "parquet": parquet_result},
    }
