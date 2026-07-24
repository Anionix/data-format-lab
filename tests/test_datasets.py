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


def test_capture_uses_the_full_timestamp_for_unique_destinations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(datasets, "_github_star_pages", lambda user, token: [])

    first = datasets.capture_github_stars(
        "octocat", tmp_path, captured_at="2026-07-14T01:02:03+00:00"
    )
    second = datasets.capture_github_stars(
        "octocat", tmp_path, captured_at="2026-07-14T01:02:04+00:00"
    )

    assert first != second


def test_capture_rejects_unsafe_login_before_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = False

    def request(user: str, token: str | None) -> list[dict]:
        nonlocal requested
        requested = True
        return []

    monkeypatch.setattr(datasets, "_github_star_pages", request)
    with pytest.raises(ValueError, match="valid login"):
        datasets.capture_github_stars("../octocat", tmp_path)
    assert requested is False


def test_capture_nonfinite_failure_leaves_no_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        datasets,
        "_github_star_pages",
        lambda user, token: [{"score": float("nan")}],
    )
    timestamp = "2026-07-14T01:02:03+00:00"

    with pytest.raises(ValueError, match="not JSON compliant"):
        datasets.capture_github_stars("octocat", tmp_path, captured_at=timestamp)

    assert not (tmp_path / "github-stars-octocat-2026-07-14T01-02-03-00-00").exists()
