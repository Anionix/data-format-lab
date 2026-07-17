from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_GEONAMES_COLUMNS = (
    "geonameid", "name", "asciiname", "alternatenames", "latitude",
    "longitude", "feature_class", "feature_code", "country_code",
    "cc2", "admin1_code", "admin2_code", "admin3_code", "admin4_code",
    "population", "elevation", "dem", "timezone", "modification_date",
)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _columns(manifest: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(str(column["name"]) for column in manifest["columns"])


def _types(manifest: Mapping[str, object]) -> dict[str, str]:
    return {
        str(column["name"]): str(column["arrow_type"])
        for column in manifest["columns"]
    }


def _write_rows(destination: Path, manifest: Mapping[str, object], rows: Iterable[Mapping[str, object]]) -> int:
    names = _columns(manifest)
    types = _types(manifest)
    count = 0
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            output: dict[str, str] = {}
            for name in names:
                value = row.get(name)
                if value is None or value == "":
                    output[name] = ""
                elif types[name] == "bool":
                    output[name] = "true" if value is True or str(value).lower() == "true" else "false"
                else:
                    output[name] = _text(value)
            writer.writerow(output)
            count += 1
    return count


def _bank_rows(raw: bytes, names: tuple[str, ...]) -> Iterable[Mapping[str, object]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        member = next(name for name in outer.namelist() if name.endswith("bank-additional.zip"))
        nested = outer.read(member)
    with zipfile.ZipFile(io.BytesIO(nested)) as inner:
        member = next(name for name in inner.namelist() if name.endswith("bank-additional-full.csv"))
        data = io.TextIOWrapper(inner.open(member), encoding="latin-1", newline="")
        with data:
            for row in csv.DictReader(data, delimiter=";"):
                yield row


def _retail_rows(raw: bytes) -> Iterable[Mapping[str, object]]:
    from openpyxl import load_workbook

    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        member = next(name for name in archive.namelist() if name.endswith("online_retail_II.xlsx"))
        workbook_bytes = archive.read(member)
    workbook = load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            iterator = sheet.iter_rows(values_only=True)
            source_names = ["Customer_ID" if value == "Customer ID" else str(value) for value in next(iterator)]
            for values in iterator:
                if not any(value is not None for value in values):
                    continue
                yield dict(zip(source_names, values, strict=False))
    finally:
        workbook.close()


def _geonames_rows(raw: bytes) -> Iterable[Mapping[str, object]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        member = next(name for name in archive.namelist() if name.endswith("cities500.txt"))
        data = io.TextIOWrapper(archive.open(member), encoding="utf-8", newline="")
        with data:
            for line in data:
                values = line.rstrip("\n").split("\t")
                if len(values) != len(_GEONAMES_COLUMNS):
                    raise ValueError(f"GeoNames row has {len(values)} fields, expected 19")
                yield dict(zip(_GEONAMES_COLUMNS, values, strict=True))


def _owid_rows(raw: bytes) -> Iterable[Mapping[str, object]]:
    text = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", newline="")
    with text:
        yield from csv.DictReader(text)


def _nyc_rows(manifest: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
    source = manifest["source"]
    if not isinstance(source, Mapping):
        raise ValueError("NYC source contract must be an object")
    target = int(source.get("snapshot_rows_target", 1_000_000))
    page_size = 50_000
    offset = 0
    while offset < target:
        limit = min(page_size, target - offset)
        params = {
            "$select": "unique_key,created_date,complaint_type,borough,descriptor AS complaint_text",
            "$where": "created_date >= '2010-01-01T00:00:00' AND created_date < '2020-01-01T00:00:00'",
            "$order": "unique_key ASC",
            "$limit": str(limit),
            "$offset": str(offset),
        }
        url = f"{source['url']}?{urlencode(params)}"
        request = Request(url, headers={"Accept": "text/csv", "User-Agent": "data-format-lab"})
        with urlopen(request, timeout=120) as response:
            page = list(csv.DictReader(io.TextIOWrapper(response, encoding="utf-8", newline="")))
        if not page:
            raise ValueError(f"NYC source ended at {offset} rows, expected {target}")
        yield from page
        offset += len(page)


def materialize_official(
    dataset_id: str,
    manifest: Mapping[str, object],
    raw: bytes,
    destination: Path,
) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "raw.bin").write_bytes(raw)
    source_format = str(manifest.get("source_format", ""))
    output = destination / "source.csv"
    if dataset_id == "uci-bank-marketing":
        rows = _bank_rows(raw, _columns(manifest))
    elif dataset_id == "uci-online-retail-ii":
        rows = _retail_rows(raw)
    elif dataset_id == "geonames-cities500":
        rows = _geonames_rows(raw)
    elif dataset_id == "owid-energy":
        rows = _owid_rows(raw)
    elif dataset_id == "nyc-311-2010-2019":
        rows = _nyc_rows(manifest)
    else:
        raise ValueError(f"no official normalizer for {dataset_id} ({source_format})")
    row_count = _write_rows(output, manifest, rows)
    (destination / "materialization.json").write_text(
        json.dumps({"dataset_id": dataset_id, "rows": row_count, "source_format": source_format}, indent=2) + "\n",
        encoding="utf-8",
    )
    return output
