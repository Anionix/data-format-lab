from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import zstandard as zstd

from .model import WorkloadSpec


API_VERSION = "2026-03-10"
_GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_SUPPORTED_ARROW_TYPES = frozenset({"string", "float64", "int64", "bool"})


def _validate_json_value(value: object, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain finite numbers")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{path} keys must be non-empty strings")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains an unsupported value")


def _validate_source_format(value: object) -> None:
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("manifest source_format must not be empty")
        return
    if not isinstance(value, Mapping):
        raise ValueError("manifest source_format must be a string or object")
    name = value.get("name", value.get("format", value.get("kind")))
    if not isinstance(name, str) or not name.strip():
        raise ValueError("manifest source_format needs a non-empty name")
    _validate_json_value(dict(value), "manifest source_format")


def _validate_columns(value: object) -> set[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("manifest columns must be a non-empty list")
    names: set[str] = set()
    for index, column in enumerate(value):
        path = f"manifest columns[{index}]"
        if not isinstance(column, Mapping):
            raise ValueError(f"{path} must be an object")
        name = column.get("name")
        arrow_type = column.get("arrow_type")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}.name must be a non-empty string")
        if name in names:
            raise ValueError(f"duplicate manifest column: {name}")
        if arrow_type not in _SUPPORTED_ARROW_TYPES:
            raise ValueError(f"unsupported arrow type for column {name}")
        nullable = column.get("nullable", True)
        if not isinstance(nullable, bool):
            raise ValueError(f"{path}.nullable must be a boolean")
        names.add(name)
    return names


def _validate_workloads(value: object, columns: set[str]) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("manifest workloads must be an object")
    if not value:
        raise ValueError("manifest workloads must not be empty")
    for operation, payload in value.items():
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("workload names must be non-empty strings")
        if not isinstance(payload, Mapping):
            raise ValueError(f"workload {operation} must be an object")
        try:
            spec = WorkloadSpec.from_mapping(operation, payload)
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError(f"invalid workload {operation}: {error}") from error
        references = (*spec.columns, *(([spec.column] if spec.column else [])))
        if any(column not in columns for column in references):
            raise ValueError(f"workload {operation} references an unknown column")


def validate_manifest(manifest: Mapping[str, object]) -> dict:
    """Validate optional source contracts and the schema used by generic runners."""
    if not isinstance(manifest, Mapping):
        raise ValueError("dataset manifest must be an object")
    if "source_format" in manifest:
        _validate_source_format(manifest["source_format"])
    if "normalization" in manifest:
        if not isinstance(manifest["normalization"], Mapping):
            raise ValueError("manifest normalization must be an object")
        _validate_json_value(dict(manifest["normalization"]), "manifest normalization")
    columns = _validate_columns(manifest["columns"]) if "columns" in manifest else set()
    if "workloads" in manifest:
        _validate_workloads(manifest["workloads"], columns)
    return dict(manifest)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(root: Path, dataset_id: str) -> dict:
    if Path(dataset_id).name != dataset_id:
        raise ValueError("dataset id must be one path segment")
    path = root / "datasets" / dataset_id / "manifest.json"
    return validate_manifest(json.loads(path.read_text(encoding="utf-8")))


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
