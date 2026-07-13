import json
from pathlib import Path

import pytest
import zstandard as zstd

from format_bench import datasets


def test_fetch_verifies_both_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = b"value\n1\n"
    archive = zstd.ZstdCompressor().compress(source)
    manifest_dir = tmp_path / "datasets" / "fixture"
    manifest_dir.mkdir(parents=True)
    manifest = {
        "asset": {
            "repository": "owner/repo",
            "release_tag": "v1",
            "name": "fixture.csv.zst",
            "compressed_sha256": datasets.sha256_bytes(archive),
        },
        "source_sha256": datasets.sha256_bytes(source),
    }
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(datasets, "_download", lambda _: archive)

    output = tmp_path / "download"
    assert datasets.fetch_dataset(tmp_path, "fixture", output).read_bytes() == source
    with pytest.raises(FileExistsError):
        datasets.fetch_dataset(tmp_path, "fixture", output)


def test_capture_is_append_only_and_records_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(datasets, "_github_star_pages", lambda user, token: [{"repo": user}])
    destination = datasets.capture_github_stars(
        "octocat", tmp_path, captured_at="2026-07-14T01:02:03+00:00"
    )
    metadata = json.loads((destination / "capture.json").read_text())
    assert metadata["api_version"] == "2026-03-10"
    assert metadata["records"] == 1
    with pytest.raises(FileExistsError):
        datasets.capture_github_stars(
            "octocat", tmp_path, captured_at="2026-07-14T01:02:03+00:00"
        )
