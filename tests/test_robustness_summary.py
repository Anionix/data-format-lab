from format_bench.robustness.summary import summarize_cases


def test_summary_ignores_malformed_duration_and_hash_evidence() -> None:
    summary = summarize_cases(
        [
            {
                "target": "csv",
                "tier": "CORE",
                "verdict": "PASS",
                "observed": "ROUNDTRIP_EQUAL",
                "process": {"duration_ms": "not-a-number"},
                "artifact_records": [
                    {"sha256": 123},
                    {"sha256": "artifact-hash"},
                    "not-a-record",
                ],
                "details": {"source_commit": ["not-a-hash"]},
            }
        ]
    )

    assert summary["csv"] == {
        "tier": "CORE",
        "cases": 1,
        "applicable": 1,
        "pass": 1,
        "fail": 0,
        "incomplete": 0,
        "crashed": 0,
        "timed_out": 0,
        "unsupported": 0,
        "harness_failed": 0,
        "budget_exhausted": 0,
        "duration_ms_p50": None,
        "artifact_sha256": ["artifact-hash"],
        "source_identities": [],
        "artifact_mutation": {
            "denominator": 0,
            "completed": 0,
            "failures": 0,
            "crashes": 0,
            "timeouts": 0,
            "unsupported": 0,
            "incomplete": 0,
            "completed_pct": None,
        },
    }


def test_summary_counts_only_artifact_mutations_and_reports_nullable_completion() -> None:
    summary = summarize_cases(
        [
            {"target": "csv", "tier": "CORE", "case_id": "rows-1", "verdict": "PASS", "observed": "ROUNDTRIP_EQUAL"},
            {
                "target": "csv",
                "tier": "CORE",
                "case_id": "malformed-truncated",
                "mutation": {"operation": "truncate"},
                "verdict": "PASS",
                "observed": "REJECTED",
            },
            {"target": "csv", "tier": "CORE", "case_id": "mutation-000", "mutation": {"recipe_id": "recipe-000", "operation": "flip"}, "verdict": "PASS", "observed": "ROUNDTRIP_EQUAL"},
            {"target": "csv", "tier": "CORE", "case_id": "mutation-001", "mutation": {"recipe_id": "recipe-001", "operation": "truncate"}, "verdict": "FAIL", "observed": "CRASHED"},
            {"target": "csv", "tier": "CORE", "case_id": "mutation-002", "mutation": {"recipe_id": "recipe-002", "operation": "flip"}, "verdict": "INCOMPLETE", "observed": "TIMED_OUT"},
            {"target": "csv", "tier": "CORE", "case_id": "mutation-003", "mutation": {"recipe_id": "recipe-003", "operation": "flip"}, "verdict": "INCOMPLETE", "observed": "UNSUPPORTED"},
        ]
    )

    assert summary["csv"]["artifact_mutation"] == {
        "denominator": 4,
        "completed": 2,
        "failures": 1,
        "crashes": 1,
        "timeouts": 1,
        "unsupported": 1,
        "incomplete": 2,
        "completed_pct": 50.0,
    }


def test_summary_uses_absent_percentage_for_no_artifact_mutations() -> None:
    summary = summarize_cases(
        [{"target": "csv", "tier": "CORE", "verdict": "PASS", "observed": "ROUNDTRIP_EQUAL"}]
    )

    assert summary["csv"]["artifact_mutation"] == {
        "denominator": 0,
        "completed": 0,
        "failures": 0,
        "crashes": 0,
        "timeouts": 0,
        "unsupported": 0,
        "incomplete": 0,
        "completed_pct": None,
    }
