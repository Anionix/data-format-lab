from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import cast

import pytest

from format_bench.dataset_sources import materialize_official


def _archive(*rows: tuple[str, ...]) -> bytes:
    payload = "".join("\t".join(row) + "\n" for row in rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("cities500.txt", payload)
    return buffer.getvalue()


def _row(
    geonameid: str, name: str, *, timezone: str = "Europe/London"
) -> tuple[str, ...]:
    return (
        geonameid,
        name,
        name,
        "",
        "51.5",
        "-0.1",
        "P",
        "PPL",
        "GB",
        "",
        "ENG",
        "",
        "",
        "",
        "1000",
        "",
        "10",
        timezone,
        "2026-07-19",
    )


def _manifest() -> dict[str, object]:
    root = Path(__file__).parents[1]
    path = root / "datasets" / "geonames-cities500" / "manifest.json"
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def test_geonames_materialization_sorts_by_numeric_id_then_full_row(
    tmp_path: Path,
) -> None:
    raw = _archive(
        _row("10", "Zulu"),
        _row("2", "Beta"),
        _row("2", "Alpha", timezone=""),
    )

    output = materialize_official(
        "geonames-cities500", _manifest(), raw, tmp_path / "normalized"
    )

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["geonameid"], row["name"]) for row in rows] == [
        ("2", "Alpha"),
        ("2", "Beta"),
        ("10", "Zulu"),
    ]
    assert rows[0]["timezone"] == ""


@pytest.mark.parametrize("field_count", [18, 20])
def test_geonames_materialization_rejects_non_19_field_rows(
    tmp_path: Path, field_count: int
) -> None:
    fields = _row("1", "London")
    malformed = fields[:field_count] if field_count == 18 else (*fields, "extra")

    with pytest.raises(
        ValueError, match=rf"GeoNames row 1 has {field_count} fields, expected 19"
    ):
        materialize_official(
            "geonames-cities500",
            _manifest(),
            _archive(malformed),
            tmp_path / f"invalid-{field_count}",
        )
