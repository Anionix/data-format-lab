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
    }
