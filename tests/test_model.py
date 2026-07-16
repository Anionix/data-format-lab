from pathlib import Path

import pytest

from format_bench.model import (
    Applicability,
    ColumnSpec,
    DatasetSpec,
    ExecutionState,
    Lane,
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
    TargetTier,
    robustness_verdict,
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
    with pytest.raises(ValueError, match="illegal evidence transition"):
        transition(ExecutionState.REPORTED, ExecutionState.FAILED)
    with pytest.raises(ValueError, match="illegal evidence transition"):
        transition(ExecutionState.REPORTED, ExecutionState.UNSUPPORTED)


def test_failure_is_available_from_an_active_state() -> None:
    assert transition(ExecutionState.ENCODED, ExecutionState.FAILED) is ExecutionState.FAILED


def test_robustness_contract_exposes_the_public_vocabulary() -> None:
    assert Lane.ROBUSTNESS == "robustness"
    assert {tier.value for tier in TargetTier} == {"CORE", "EXPERIMENTAL"}
    assert {verdict.value for verdict in RobustnessVerdict} == {
        "PASS",
        "FAIL",
        "NOT_APPLICABLE",
        "INCOMPLETE",
    }


@pytest.mark.parametrize(
    ("expectation", "observed", "verdict"),
    [
        ("MUST_ROUNDTRIP", "ROUNDTRIP_EQUAL", "PASS"),
        ("MUST_ROUNDTRIP", "REJECTED", "FAIL"),
        ("MUST_REJECT", "REJECTED", "PASS"),
        ("MUST_REJECT", "ACCEPTED", "FAIL"),
        ("MUST_NOT_CRASH", "ACCEPTED", "PASS"),
        ("MUST_NOT_CRASH", "REJECTED", "PASS"),
        ("MUST_NOT_CRASH", "CRASHED", "FAIL"),
        ("MUST_NOT_CRASH", "TIMED_OUT", "FAIL"),
        ("MUST_NOT_CRASH", "TARGET_FAILED", "FAIL"),
        ("MUST_NOT_CRASH", "UNSUPPORTED", "INCOMPLETE"),
        ("MUST_NOT_CRASH", "BUDGET_EXHAUSTED", "INCOMPLETE"),
        ("MUST_NOT_CRASH", "HARNESS_FAILED", "INCOMPLETE"),
    ],
)
def test_robustness_verdict_is_derived_from_expectation_and_observation(
    expectation: str, observed: str, verdict: str
) -> None:
    assert robustness_verdict(
        RobustnessExpectation(expectation), ObservedOutcome(observed)
    ) is RobustnessVerdict(verdict)


def test_not_applicable_takes_precedence_over_observation() -> None:
    assert robustness_verdict(
        RobustnessExpectation.MUST_ROUNDTRIP,
        ObservedOutcome.CRASHED,
        Applicability.NOT_APPLICABLE,
    ) is RobustnessVerdict.NOT_APPLICABLE


def test_robustness_verdict_normalizes_persisted_strings() -> None:
    assert robustness_verdict("MUST_ROUNDTRIP", "REJECTED") is RobustnessVerdict.FAIL
    assert robustness_verdict("MUST_REJECT", "REJECTED") is RobustnessVerdict.PASS


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
    with pytest.raises(TypeError):
        spec.expected_counts["rows"] = 2

    unsafe = DatasetSpec(**{**spec.__dict__, "asset_name": "../source.csv"})
    with pytest.raises(ValueError, match="safe relative path"):
        unsafe.asset_path(Path("datasets"))
