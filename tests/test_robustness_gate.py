import json
from pathlib import Path

import pytest

from format_bench.robustness.gate import core_blockers, core_failures, main


def _case(
    tier: str, verdict: str, case_id: str, observed: str | None = None
) -> dict[str, object]:
    case = {
        "target": "fixture",
        "tier": tier,
        "case_id": case_id,
        "verdict": verdict,
    }
    if observed is not None:
        case["observed"] = observed
    return case


def _payload(cases: list[dict[str, object]]) -> dict[str, object]:
    return {
        "profile": "robustness",
        "results": {"robustness_v1": {"cases": cases}},
    }


def test_core_failures_exclude_incomplete_and_experimental_cases() -> None:
    failed = _case("CORE", "FAIL", "core-fail")
    payload = _payload(
        [
            _case("CORE", "PASS", "core-pass"),
            _case("CORE", "INCOMPLETE", "core-incomplete"),
            failed,
            _case("EXPERIMENTAL", "FAIL", "experimental-fail"),
        ]
    )

    assert core_failures(payload) == [failed]


def test_core_blockers_include_incomplete_and_harness_failures() -> None:
    incomplete = _case("CORE", "INCOMPLETE", "core-incomplete")
    harness_failed = _case(
        "CORE", "PASS", "core-harness-failed", observed="HARNESS_FAILED"
    )

    assert core_blockers(_payload([incomplete, harness_failed])) == [
        incomplete,
        harness_failed,
    ]


@pytest.mark.parametrize(
    "cases",
    [
        [_case("CORE", "FAIL", "bad")],
        [_case("CORE", "INCOMPLETE", "incomplete")],
        [_case("CORE", "PASS", "harness-failed", observed="HARNESS_FAILED")],
    ],
)
def test_gate_exits_for_non_passing_core_evidence(
    cases: list[dict[str, object]],
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(_payload(cases)))

    with pytest.raises(SystemExit) as error:
        main([str(path)])

    assert error.value.code == 1
    assert "core robustness gate blocked" in capsys.readouterr().err


def test_gate_rejects_missing_core_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(_payload([_case("EXPERIMENTAL", "PASS", "optional")])))

    with pytest.raises(SystemExit) as error:
        main([str(path)])

    assert error.value.code == 1
    assert "no CORE cases" in capsys.readouterr().err


def test_gate_keeps_experimental_failure_non_blocking(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            _payload(
                [
                    _case("CORE", "PASS", "good"),
                    _case("EXPERIMENTAL", "FAIL", "evidence"),
                ]
            )
        )
    )

    main([str(path)])

    assert "1 core cases, 1 experimental observations" in capsys.readouterr().out


def test_gate_rejects_malformed_case(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(_payload([_case("UNKNOWN", "FAIL", "bad-tier")])))

    with pytest.raises(ValueError, match="invalid target tier"):
        main([str(path)])
