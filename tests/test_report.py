import json
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
        "formats": [
            {
                "format": "csv",
                "comparability": "FULL_COMPARABLE",
                "state": "BENCHMARKED",
                "native_bytes": 10,
                "transport_zstd_bytes": 8,
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
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "results.json").write_text(json.dumps(results))

    report = render_report(tmp_path).read_text()

    assert "| csv | read_all | 1 | 1 | 2 | 1 | 4 | abc123 | 100 |" in report
    reported = json.loads((tmp_path / "manifest.json").read_text())
    assert reported["formats"][0]["state"] == "REPORTED"
    assert render_report(tmp_path).read_text() == report


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
                    "attempts": [{"result": "failed build"}],
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
