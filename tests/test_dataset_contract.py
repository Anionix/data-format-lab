from __future__ import annotations

from pathlib import Path

import pytest

from format_bench.datasets import load_manifest, validate_manifest


def _manifest(**overrides: object) -> dict:
    manifest = {
        "dataset_id": "fixture",
        "source_format": {"name": "csv", "compression": "zstd"},
        "normalization": {
            "encoding": "utf-8",
            "null_values": [""],
            "trim_whitespace": False,
        },
        "columns": [
            {"name": "name", "arrow_type": "string"},
            {"name": "amount", "arrow_type": "int64", "nullable": False},
        ],
        "workloads": {
            "read_all": {"kind": "read_all"},
            "project": {"kind": "projection", "columns": ["name"]},
            "popular": {
                "kind": "filter",
                "column": "amount",
                "operator": "gt",
                "value": 10,
            },
        },
    }
    manifest.update(overrides)
    return manifest


def test_validate_manifest_accepts_generic_contract() -> None:
    manifest = _manifest()

    assert validate_manifest(manifest) == manifest


def test_validate_manifest_rejects_empty_workload_contract() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_manifest(_manifest(workloads={}))


def test_validate_manifest_keeps_legacy_release_manifest_compatible() -> None:
    root = Path(__file__).parents[1]

    manifest = load_manifest(root, "github-stars-2026-07-03")

    assert manifest["asset"]["name"].endswith(".csv.zst")
    assert manifest["columns"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_format", {"compression": "zstd"}, "needs a non-empty name"),
        ("normalization", ["utf-8"], "must be an object"),
        ("columns", [{"name": "x"}], "unsupported arrow type"),
        ("columns", [{"name": "x", "arrow_type": "string"}, {"name": "x", "arrow_type": "string"}], "duplicate"),
        ("workloads", {"project": {"kind": "projection", "columns": ["missing"]}}, "unknown column"),
    ],
)
def test_validate_manifest_rejects_unsafe_contract_fields(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_manifest(_manifest(**{field: value}))


def test_validate_manifest_rejects_non_json_normalization_values() -> None:
    with pytest.raises(ValueError, match="unsupported value"):
        validate_manifest(_manifest(normalization={"callback": object()}))
