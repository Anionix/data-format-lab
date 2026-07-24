import tomllib
from pathlib import Path
from typing import NotRequired, get_origin, get_type_hints

from format_bench.formats import (
    AdapterManifest,
    FormatAdapter,
    VerificationResult,
)


def test_format_adapter_uses_named_manifest_and_verification_contracts() -> None:
    read_hints = get_type_hints(FormatAdapter.read)
    verify_hints = get_type_hints(FormatAdapter.verify_roundtrip)
    scan_hints = get_type_hints(FormatAdapter.scan, localns={"Operation": object})

    assert read_hints["manifest"] is AdapterManifest
    assert verify_hints["manifest"] is AdapterManifest
    assert verify_hints["return"] is VerificationResult
    assert scan_hints["manifest"] is AdapterManifest


def test_adapter_contract_keys_are_explicit() -> None:
    manifest_hints = get_type_hints(AdapterManifest, include_extras=True)
    assert set(manifest_hints) == {
        "canonical_hash",
        "columns",
        "expected_counts",
        "rows",
        "workloads",
    }
    assert get_origin(manifest_hints["workloads"]) is NotRequired
    assert set(get_type_hints(VerificationResult)) == {
        "canonical_hash",
        "counts",
        "passed",
    }
    assert AdapterManifest.__required_keys__ == {
        "canonical_hash",
        "columns",
        "expected_counts",
        "rows",
    }
    assert AdapterManifest.__optional_keys__ == {"workloads"}


def test_adapter_contract_is_in_the_blocking_strict_frontier() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    pyright = pyproject["tool"]["pyright"]

    assert pyright["typeCheckingMode"] == "strict"
    assert "src/format_bench/adapter_contract.py" in pyright["include"]
