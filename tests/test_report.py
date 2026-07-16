import json
import hashlib
from pathlib import Path

import pytest

from format_bench.report import render_report


def test_prompt_report_is_deterministic_and_includes_exact_tokens(tmp_path: Path) -> None:
    manifest = {"state": "BENCHMARKED", "dataset_id": "fixture"}
    results = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "run_id": "prompt-fixture",
        "profile": "prompt",
        "environment": {
            "git_commit": "abc",
            "flake_lock_sha256": "def",
            "platform": "test-os",
            "machine": "test-cpu",
            "python": "3.12.0",
        },
        "results": {
            "prompt_v1": {
                "state": "BENCHMARKED",
                "metrics": {
                    "corpus": {
                        "compact_tsv": {
                            "payload_bytes": 10,
                            "taxonomy_bytes": 4,
                            "schema_bytes": 2,
                            "total_bytes": 16,
                            "tokens": {"o200k_base": 3, "cl100k_base": 4},
                        }
                    },
                    "retrieval_to_compact_tsv": {
                        "5": {
                            "rows": 5,
                            "bytes": 8,
                            "tokens": {"o200k_base": 2, "cl100k_base": 3},
                        }
                    },
                }
            }
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))
    path = render_report(tmp_path)
    first = path.read_text()
    assert "| compact_tsv | 10 | 4 | 2 | 16 | 3 | 4 |" in first
    assert "Direct token counts for binary formats are N/A." in first
    assert json.loads((tmp_path / "manifest.json").read_text())["state"] == "REPORTED"
    reported = json.loads((tmp_path / "results.json").read_text())
    assert reported["state"] == "REPORTED"
    assert reported["results"]["prompt_v1"]["state"] == "REPORTED"
    assert render_report(tmp_path).read_text() == first


def test_report_rejects_unbenchmarked_evidence(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text('{"state":"ROUNDTRIP_VERIFIED"}')
    (tmp_path / "results.json").write_text('{"state":"BENCHMARKED"}')
    with pytest.raises(ValueError, match="requires benchmarked"):
        render_report(tmp_path)


def test_fair_report_includes_normalized_result_hash(tmp_path: Path) -> None:
    manifest = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "rankable": True,
        "seed": 20260703,
        "input": {"source": "input/source.csv", "manifest": "input/manifest.json"},
        "environment": {
            "git_commit": "encoding-commit",
            "flake_lock_sha256": "encoding-flake",
            "platform": "encoding-os",
            "machine": "encoding-cpu",
            "python": "3.12.0",
            "packages": {"pyarrow": "22.0.0"},
        },
        "formats": [
            {
                "format": "csv",
                "comparability": "FULL_COMPARABLE",
                "state": "BENCHMARKED",
                "native_bytes": 10,
                "transport_zstd_bytes": 8,
                "settings": {"delimiter": ","},
            }
        ],
    }
    results = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "run_id": "fair-fixture",
        "profile": "fair",
        "environment": {
            "git_commit": "abc",
            "flake_lock_sha256": "def",
            "platform": "test-os",
            "machine": "test-cpu",
            "python": "3.12.0",
            "packages": {"pyarrow": "23.0.1"},
        },
        "measurement": {
            "fresh_processes": 10,
            "warmups": 5,
            "iterations": 30,
            "seed": 20260703,
            "timeout_seconds": 120,
            "os_cache_purged": False,
        },
        "results": {
            "csv/read_all": {
                "status": "MEASURED",
                "fresh_process": {"p50_ms": 1},
                "warm": {"p50_ms": 1, "p95_ms": 2, "iqr_ms": 1},
                "result": 4,
                "evidence": {"normalized_hash": "abc123"},
                "max_rss_bytes_p50": 100,
            }
        },
    }
    (tmp_path / "input").mkdir()
    source = tmp_path / "input" / "source.csv"
    source.write_bytes(b"source\n")
    (tmp_path / "input" / "manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "canonical_hash": "canonical-sha",
                "rows": 4,
                "columns": [{"name": "value"}],
                "expected_counts": {"rows": 4},
            }
        )
    )
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))

    report = render_report(tmp_path).read_text()

    assert "| csv | read_all | 1 | 1 | 2 | 1 | 4 | abc123 | 100 |" in report
    assert f"| Input SHA-256 | {hashlib.sha256(source.read_bytes()).hexdigest()} |" in report
    assert "| Canonical hash | canonical-sha |" in report
    assert "| Rows / columns | 4 / 1 |" in report
    assert "| PyArrow | 23.0.1 |" in report
    assert "| Git commit | encoding-commit |" in report
    assert "| Git commit | abc |" in report
    assert "| Packages | {\"pyarrow\":\"22.0.0\"} |" in report
    assert "| Packages | {\"pyarrow\":\"23.0.1\"} |" in report
    assert "| Protocol | 10 fresh processes; 5 warmups; 30 measurements; timeout 120s |" in report
    assert "| csv | {\"delimiter\":\",\"} |" in report
    reported = json.loads((tmp_path / "manifest.json").read_text())
    assert reported["formats"][0]["state"] == "REPORTED"
    assert render_report(tmp_path).read_text() == report


def test_fair_report_includes_reproducibility_provenance(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "source.csv"
    source.write_text("value\n1\n")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    (input_dir / "manifest.json").write_text(
        json.dumps(
            {
                "rows": 1,
                "columns": [{"name": "value", "arrow_type": "int64", "nullable": True}],
                "source_sha256": source_sha256,
                "canonical_hash": "canonical-hash",
                "expected_counts": {"rows": 1},
            }
        )
    )
    manifest = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "rankable": True,
        "input": {"source": "input/source.csv", "manifest": "input/manifest.json"},
        "formats": [
            {
                "format": "csv",
                "comparability": "FULL_COMPARABLE",
                "state": "BENCHMARKED",
                "native_bytes": 10,
                "settings": {"compression": "none"},
            }
        ],
    }
    results = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "run_id": "fair-provenance-fixture",
        "profile": "fair",
        "measurement": {
            "fresh_processes": 10,
            "warmups": 5,
            "iterations": 30,
            "seed": 20260703,
            "os_cache_purged": False,
            "timeout_seconds": 120,
        },
        "environment": {
            "git_commit": "abc",
            "flake_lock_sha256": "def",
            "platform": "test-os",
            "machine": "test-cpu",
            "python": "3.12.0",
            "packages": {"pyarrow": "23.0.1"},
        },
        "release": {
            "archive_url": "https://example.invalid/evidence.tar.zst",
            "checksum_url": "https://example.invalid/evidence.tar.zst.sha256",
        },
        "results": {
            "csv/read_all": {
                "status": "MEASURED",
                "fresh_process": {"p50_ms": 1},
                "warm": {"p50_ms": 1, "p95_ms": 2, "iqr_ms": 1},
                "result": 1,
                "evidence": {"normalized_hash": "result-hash"},
                "max_rss_bytes_p50": 100,
            }
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))

    report = render_report(tmp_path).read_text()

    assert "## Reproducibility" in report
    assert f"| Input SHA-256 | {source_sha256} |" in report
    assert "| Canonical hash | canonical-hash |" in report
    assert "| Protocol | 10 fresh processes; 5 warmups; 30 measurements; timeout 120s |" in report
    assert "| PyArrow | 23.0.1 |" in report
    assert '| csv | {"compression":"none"} |' in report
    assert "## Evidence Digests" in report
    assert "## Durable Evidence" in report
    assert "https://example.invalid/evidence.tar.zst.sha256" in report
    results_hash = hashlib.sha256((tmp_path / "results.json").read_bytes()).hexdigest()
    assert results_hash in report


def test_report_failure_does_not_persist_reported_state(tmp_path: Path) -> None:
    (tmp_path / "input").mkdir()
    (tmp_path / "input/source.csv").write_text("value\n1\n")
    (tmp_path / "input/manifest.json").write_text(
        json.dumps({"source_sha256": "wrong", "canonical_hash": "canonical"})
    )
    manifest = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "rankable": True,
        "input": {"source": "input/source.csv", "manifest": "input/manifest.json"},
        "formats": [],
    }
    results = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "run_id": "failed-report-fixture",
        "profile": "fair",
        "environment": {},
        "measurement": {},
        "results": {},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))

    with pytest.raises(ValueError, match="input source SHA-256 mismatch"):
        render_report(tmp_path)

    assert json.loads((tmp_path / "manifest.json").read_text())["state"] == "BENCHMARKED"
    assert json.loads((tmp_path / "results.json").read_text())["state"] == "BENCHMARKED"


def test_claim_report_preserves_terminal_observations(tmp_path: Path) -> None:
    manifest = {"state": "BENCHMARKED", "dataset_id": "fixture", "formats": []}
    results = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "run_id": "claims-fixture",
        "profile": "claims",
        "environment": {
            "git_commit": "abc",
            "flake_lock_sha256": "def",
            "platform": "test-os",
            "machine": "test-cpu",
            "python": "3.12.0",
        },
        "results": {
            "measured": {
                "comparability": "FULL_COMPARABLE",
                "state": "BENCHMARKED",
                "failure_reason": None,
            },
            "unsupported": {
                "comparability": "ADAPTED",
                "state": "UNSUPPORTED",
                "failure_reason": "missing dependency",
            },
            "negative_research": {
                "partial": {
                    "comparability": "PARTIAL",
                    "state": "FAILED",
                    "claim_summary": "failed build",
                    "attempts": [{"result": "robustness crash"}],
                }
            },
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))

    render_report(tmp_path)

    reported = json.loads((tmp_path / "results.json").read_text())["results"]
    assert reported["measured"]["state"] == "REPORTED"
    assert reported["unsupported"]["state"] == "UNSUPPORTED"
    assert reported["negative_research"]["partial"]["state"] == "FAILED"
    assert "failed build" in (tmp_path / "report.md").read_text()
    assert "robustness crash" not in (tmp_path / "report.md").read_text()


def test_claim_report_falls_back_to_legacy_research_attempt(tmp_path: Path) -> None:
    manifest = {"state": "BENCHMARKED", "dataset_id": "fixture", "formats": []}
    results = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "run_id": "legacy-claims-fixture",
        "profile": "claims",
        "environment": {
            "git_commit": "abc",
            "flake_lock_sha256": "def",
            "platform": "test-os",
            "machine": "test-cpu",
            "python": "3.12.0",
        },
        "results": {
            "negative_research": {
                "legacy": {
                    "comparability": "PARTIAL",
                    "state": "FAILED",
                    "attempts": [{"result": "legacy result"}],
                }
            }
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))

    render_report(tmp_path)

    assert "| legacy | RESEARCH_RECORD | PARTIAL | FAILED | legacy result |" in (
        tmp_path / "report.md"
    ).read_text()


def test_robustness_report_separates_case_contract_and_is_deterministic(
    tmp_path: Path,
) -> None:
    manifest = {"state": "BENCHMARKED", "dataset_id": "fixture"}
    results = {
        "state": "BENCHMARKED",
        "dataset_id": "fixture",
        "run_id": "robustness-fixture",
        "profile": "robustness",
        "environment": {
            "git_commit": "abc",
            "flake_lock_sha256": "def",
            "platform": "test-os",
            "machine": "test-cpu",
            "python": "3.12.0",
        },
        "results": {
            "robustness_v1": {
                "contract_version": "1",
                "state": "BENCHMARKED",
                "suite": "bounded",
                "config": {
                    "seed": 7,
                    "generated_cases": 8,
                    "mutations_per_target": 9,
                    "case_timeout_seconds": 1.5,
                    "artifact_budget_mib": 64,
                },
                "summary": {
                    "PASS": 1,
                    "FAIL": 0,
                    "NOT_APPLICABLE": 0,
                    "INCOMPLETE": 0,
                },
                "cases": [
                    {
                        "target": "csv", "tier": "CORE", "details": {"engine": "coverage-guided"}, "case_id": "rows-1",
                        "expectation": "MUST_ROUNDTRIP",
                        "observed": "ROUNDTRIP_EQUAL", "verdict": "PASS",
                    },
                ],
            }
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))

    first = render_report(tmp_path).read_text()

    assert "non-ranking evidence" in first
    assert "| Seed | 7 |" in first
    assert "| Verdict | Cases |" in first
    assert "### Target Summary" in first
    assert "### Evidence Identities" in first
    assert "| Target | Tier | Engine | Case | Expectation | Observed | Verdict |" in first
    assert "| csv | CORE | coverage-guided | rows-1 | MUST_ROUNDTRIP | ROUNDTRIP_EQUAL | PASS |" in first
    reported = json.loads((tmp_path / "results.json").read_text())
    assert reported["results"]["robustness_v1"]["state"] == "REPORTED"
    assert reported["results"]["robustness_v1"]["target_summary"]["csv"]["pass"] == 1
    assert render_report(tmp_path).read_text() == first
