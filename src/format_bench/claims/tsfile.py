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


def _write_datasets(
    tsfile_path: Path, parquet_path: Path, devices: int, points: int
) -> dict[str, float]:
    from tsfile import Tablet, TsFileTableWriter

    schema, names, types = _schema()
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
    return {
        "tsfile": round(tsfile_ms, 3),
        "parquet": round((time.perf_counter_ns() - started) / 1_000_000, 3),
    }


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
    writes = _write_datasets(tsfile_path, parquet_path, devices, points_per_device)
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
        "bytes": {"tsfile": tsfile_path.stat().st_size, "parquet": parquet_path.stat().st_size},
        "timing": {"tsfile": ts_result, "parquet": parquet_result},
    }
