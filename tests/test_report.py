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
                "metrics": {
                    "corpus": {
                        "compact_tsv": {
                            "payload_bytes": 10,
                            "taxonomy_bytes": 4,
                            "total_bytes": 14,
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
    assert "| compact_tsv | 10 | 4 | 14 | 3 | 4 |" in first
    assert "Direct token counts for binary formats are N/A." in first
    assert json.loads((tmp_path / "manifest.json").read_text())["state"] == "REPORTED"
    assert json.loads((tmp_path / "results.json").read_text())["state"] == "REPORTED"
    assert render_report(tmp_path).read_text() == first


def test_report_rejects_unbenchmarked_evidence(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text('{"state":"ROUNDTRIP_VERIFIED"}')
    (tmp_path / "results.json").write_text('{"state":"BENCHMARKED"}')
    with pytest.raises(ValueError, match="requires benchmarked"):
        render_report(tmp_path)
