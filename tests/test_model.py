from pathlib import Path

import pytest

from format_bench.model import (
    ColumnSpec,
    DatasetSpec,
    ExecutionState,
    transition,
)


def test_lifecycle_accepts_the_public_contract() -> None:
    state = ExecutionState.DISCOVERED
    for target in (
        ExecutionState.ENCODED,
        ExecutionState.ROUNDTRIP_VERIFIED,
        ExecutionState.BENCHMARKED,
        ExecutionState.REPORTED,
    ):
        state = transition(state, target)
    assert state is ExecutionState.REPORTED


def test_lifecycle_rejects_skipped_or_terminal_transitions() -> None:
    with pytest.raises(ValueError, match="illegal evidence transition"):
        transition(ExecutionState.DISCOVERED, ExecutionState.BENCHMARKED)
    with pytest.raises(ValueError, match="illegal evidence transition"):
        transition(ExecutionState.FAILED, ExecutionState.DISCOVERED)


def test_failure_is_available_from_an_active_state() -> None:
    assert transition(ExecutionState.ENCODED, ExecutionState.FAILED) is ExecutionState.FAILED


def test_dataset_asset_path_stays_under_the_run_root() -> None:
    spec = DatasetSpec(
        schema_version="1",
        dataset_id="fixture",
        asset_name="source.csv",
        source_sha256="0" * 64,
        canonical_hash="1" * 64,
        rows=1,
        columns=(ColumnSpec("value", "string"),),
        expected_counts={"rows": 1},
    )
    assert spec.asset_path(Path("datasets")) == Path("datasets/source.csv")

    unsafe = DatasetSpec(**{**spec.__dict__, "asset_name": "../source.csv"})
    with pytest.raises(ValueError, match="safe relative path"):
        unsafe.asset_path(Path("datasets"))
