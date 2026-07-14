from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import zstandard as zstd


API_VERSION = "2026-03-10"
_GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(root: Path, dataset_id: str) -> dict:
    if Path(dataset_id).name != dataset_id:
        raise ValueError("dataset id must be one path segment")
    path = root / "datasets" / dataset_id / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _download(url: str) -> bytes:
    with urlopen(url, timeout=60) as response:
        return response.read()


def fetch_dataset(root: Path, dataset_id: str, output: Path | None = None) -> Path:
    manifest = load_manifest(root, dataset_id)
    asset = manifest["asset"]
    url = (
        f"https://github.com/{asset['repository']}/releases/download/"
        f"{asset['release_tag']}/{asset['name']}"
    )
    archive = _download(url)
    if sha256_bytes(archive) != asset["compressed_sha256"]:
        raise ValueError("compressed dataset SHA-256 mismatch")
    source = zstd.ZstdDecompressor().decompress(archive)
    if sha256_bytes(source) != manifest["source_sha256"]:
        raise ValueError("dataset source SHA-256 mismatch")

    destination = output or root / ".data" / dataset_id
    destination.mkdir(parents=True, exist_ok=False)
    (destination / asset["name"]).write_bytes(archive)
    source_path = destination / "source.csv"
    source_path.write_bytes(source)
    return source_path


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for target, relation in re.findall(r'<([^>]+)>; rel="([^"]+)"', header):
        if relation == "next":
            return target
    return None


def _github_star_pages(user: str, token: str | None) -> list[dict]:
    url: str | None = f"https://api.github.com/users/{quote(user)}/starred?per_page=100"
    records: list[dict] = []
    while url:
        headers = {
            "Accept": "application/vnd.github.star+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "data-format-lab",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with urlopen(Request(url, headers=headers), timeout=60) as response:
            records.extend(json.load(response))
            url = _next_link(response.headers.get("Link"))
    return records


def capture_github_stars(
    user: str,
    output: Path,
    *,
    captured_at: str | None = None,
) -> Path:
    if _GITHUB_LOGIN.fullmatch(user) is None:
        raise ValueError("GitHub user must be a valid login")
    timestamp = captured_at or datetime.now(timezone.utc).isoformat()
    timestamp_slug = re.sub(r"[^A-Za-z0-9]+", "-", timestamp).strip("-")
    if not timestamp_slug:
        raise ValueError("capture timestamp must contain a letter or digit")
    destination = output / f"github-stars-{user}-{timestamp_slug}"
    if destination.exists():
        raise FileExistsError(destination)
    records = _github_star_pages(user, os.environ.get("GITHUB_TOKEN"))
    destination.mkdir(parents=True, exist_ok=False)
    endpoint = f"https://api.github.com/users/{quote(user)}/starred?per_page=100"
    (destination / "raw.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = {
        "schema_version": "1",
        "captured_at": timestamp,
        "api_version": API_VERSION,
        "endpoint": endpoint,
        "records": len(records),
        "authenticated": bool(os.environ.get("GITHUB_TOKEN")),
    }
    (destination / "capture.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return destination
