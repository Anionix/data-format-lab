from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class CaptureState(StrEnum):
    STARTED = "CAPTURE_STARTED"
    CAPTURED = "CAPTURED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


_CAPTURE_TRANSITIONS: dict[CaptureState | None, frozenset[CaptureState]] = {
    None: frozenset({CaptureState.STARTED}),
    CaptureState.STARTED: frozenset({CaptureState.CAPTURED, CaptureState.FAILED}),
    CaptureState.CAPTURED: frozenset({CaptureState.COMPLETE, CaptureState.FAILED}),
    CaptureState.FAILED: frozenset(),
    CaptureState.COMPLETE: frozenset(),
}


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    raw = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{context} keys must be strings")
    return {cast(str, key): item for key, item in raw.items()}


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _get(url: str, accept: str) -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": "data-format-lab/0.2"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _persist_capture(destination: Path, evidence: dict[str, object]) -> None:
    (destination / "capture.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def _write_capture(
    destination: Path,
    evidence: dict[str, object],
    status: CaptureState,
    error: BaseException | None = None,
) -> None:
    current_raw = evidence.get("status")
    current = CaptureState(current_raw) if isinstance(current_raw, str) else None
    if status not in _CAPTURE_TRANSITIONS[current]:
        raise ValueError(f"invalid NYC capture transition: {current} -> {status}")
    evidence["status"] = status
    if status == CaptureState.COMPLETE:
        evidence["lifecycle_status"] = "ENCODED"
    elif status == CaptureState.FAILED:
        evidence["lifecycle_status"] = "FAILED"
    if status in (CaptureState.COMPLETE, CaptureState.FAILED):
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
    if error is not None:
        evidence["failure_reason"] = f"{type(error).__name__}: {error}"
    _persist_capture(destination, evidence)


def finalize_capture(destination: Path, status: CaptureState, error: BaseException | None = None) -> None:
    raw_evidence = json.loads((destination / "capture.json").read_text(encoding="utf-8"))
    if not isinstance(raw_evidence, dict):
        raise ValueError("NYC capture evidence must be an object")
    evidence = cast(dict[str, object], raw_evidence)
    _write_capture(destination, evidence, status, error)


def fail_active_capture(destination: Path, error: BaseException) -> None:
    raw_evidence = json.loads((destination / "capture.json").read_text(encoding="utf-8"))
    if not isinstance(raw_evidence, dict):
        raise ValueError("NYC capture evidence must be an object")
    evidence = cast(dict[str, object], raw_evidence)
    if evidence.get("status") in (CaptureState.STARTED, CaptureState.CAPTURED):
        _write_capture(destination, evidence, CaptureState.FAILED, error)


def nyc_rows(manifest: Mapping[str, object], destination: Path) -> Iterator[Mapping[str, object]]:
    source = _mapping(manifest.get("source"), "NYC source")
    capture = _mapping(source.get("future_capture"), "NYC future capture")
    query = _mapping(capture.get("query"), "NYC query")
    pagination = _mapping(capture.get("pagination"), "NYC pagination")
    consistency = _mapping(capture.get("consistency"), "NYC consistency")
    raw_select = query.get("select")
    raw_columns = manifest.get("columns")
    if not isinstance(raw_select, list) or not raw_select:
        raise ValueError("NYC query select must be a non-empty list")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError("NYC manifest columns must be a non-empty list")
    select = tuple(_text(item, "NYC select item") for item in cast(list[object], raw_select))
    output_columns = tuple(
        _text(_mapping(item, "NYC column").get("name"), "NYC column name") for item in cast(list[object], raw_columns)
    )
    cursor = _text(pagination.get("cursor_column"), "NYC cursor")
    order = _text(query.get("order"), "NYC order")
    page_size = pagination.get("page_size")
    target = source.get("snapshot_rows_target")
    if pagination.get("strategy") != "keyset" or order.casefold() != f"{cursor} asc".casefold():
        raise ValueError("NYC pagination must use its ascending keyset cursor")
    safeguards = (
        "require_unchanged_during_capture",
        "retain_raw_metadata",
        "retain_raw_pages",
    )
    if any(consistency.get(name) is not True for name in safeguards):
        raise ValueError("NYC consistency safeguards must be enabled")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (page_size, target)):
        raise ValueError("NYC page size and row target must be positive integers")
    assert isinstance(page_size, int) and isinstance(target, int)

    source_id = _text(source.get("dataset_id"), "NYC dataset id")
    source_url = _text(source.get("url"), "NYC source URL")
    metadata_url = _text(source.get("metadata_url"), "NYC metadata URL")
    revision_field = _text(consistency.get("metadata_revision_field"), "NYC revision field")
    cursor_type = _text(pagination.get("cursor_source_type"), "NYC cursor source type")

    def metadata_revision(raw: bytes) -> str:
        payload = _mapping(json.loads(raw), "NYC metadata")
        if payload.get("id") != source_id:
            raise ValueError("NYC metadata dataset id mismatch")
        revision = payload.get(revision_field)
        if isinstance(revision, bool) or not isinstance(revision, (str, int)):
            raise ValueError("NYC metadata revision is missing or invalid")
        return str(revision)

    if cursor != ":id" or cursor_type != "socrata_system_id" or cursor not in select:
        raise ValueError("NYC keyset must use the selected Socrata :id system field")
    raw_pages = destination / "raw-pages"
    revision: dict[str, object] = {
        "field": revision_field,
        "before": None,
        "after": None,
        "matched": False,
        "metadata_before_sha256": None,
        "metadata_after_sha256": None,
    }
    pages: list[dict[str, object]] = []
    evidence: dict[str, object] = {
        "schema_version": "1",
        "dataset_id": source_id,
        "source_url": source_url,
        "metadata_url": metadata_url,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "DISCOVERED",
        "revision": revision,
        "raw_pages": pages,
    }
    last_cursor: str | None = None
    seen_cursors: set[str] = set()
    emitted = 0
    # LLM contract: a durable CAPTURE_STARTED record precedes all network I/O.
    _write_capture(destination, evidence, CaptureState.STARTED)
    try:
        raw_pages.mkdir()
        metadata_before = _get(metadata_url, "application/json")
        (destination / "metadata-before.json").write_bytes(metadata_before)
        revision["metadata_before_sha256"] = _sha256(metadata_before)
        revision_before = metadata_revision(metadata_before)
        revision["before"] = revision_before
        while emitted < target:
            limit = min(page_size, target - emitted)
            where = _text(query.get("where"), "NYC where")
            if last_cursor is not None:
                escaped = last_cursor.replace("'", "''")
                where = f"({where}) AND {cursor} > '{escaped}'"
            params = {
                "$select": ",".join(select),
                "$where": where,
                "$order": order,
                "$limit": str(limit),
            }
            raw_page = _get(f"{source_url}?{urlencode(params)}", "text/csv")
            page_name = f"page-{len(pages):05d}.csv"
            (raw_pages / page_name).write_bytes(raw_page)
            page_evidence: dict[str, object] = {
                "path": f"raw-pages/{page_name}",
                "sha256": _sha256(raw_page),
                "request": params,
                "status": "RECEIVED",
            }
            pages.append(page_evidence)
            reader = csv.DictReader(io.StringIO(raw_page.decode("utf-8-sig")))
            if tuple(reader.fieldnames or ()) != (cursor, *output_columns):
                raise ValueError("NYC page columns do not match the manifest")
            rows = list(reader)
            if not rows:
                raise ValueError(f"NYC source ended at {emitted} rows, expected {target}")
            first_cursor = _text(rows[0].get(cursor), "NYC page cursor")
            for row in rows:
                value = _text(row.get(cursor), "NYC row cursor")
                if value in seen_cursors:
                    raise ValueError("NYC keyset cursor repeated")
                seen_cursors.add(value)
            last_cursor = _text(rows[-1].get(cursor), "NYC row cursor")
            page_evidence.update(
                status="VALIDATED",
                rows=len(rows),
                first_cursor=first_cursor,
                last_cursor=last_cursor,
            )
            emitted += len(rows)
            if emitted > target:
                raise ValueError("NYC source returned more rows than requested")
            # LLM contract: PAGE_VALIDATED -> EVIDENCE_PERSISTED -> ROWS_YIELDED.
            _persist_capture(destination, evidence)
            for row in rows:
                row.pop(cursor)
                yield row

        metadata_after = _get(metadata_url, "application/json")
        (destination / "metadata-after.json").write_bytes(metadata_after)
        revision["metadata_after_sha256"] = _sha256(metadata_after)
        revision_after = metadata_revision(metadata_after)
        revision.update(
            after=revision_after,
            matched=revision_after == revision_before,
        )
        if revision_after != revision_before:
            raise ValueError("NYC source revision changed during capture")
        # LLM contract: CAPTURE_STARTED -> CAPTURED preserves DISCOVERED until
        # normalized materialization can atomically advance DISCOVERED -> ENCODED.
        _write_capture(destination, evidence, CaptureState.CAPTURED)
    except GeneratorExit:
        raise
    except BaseException as error:
        # LLM contract: any CAPTURE_STARTED/CAPTURED error -> FAILED with evidence.
        _write_capture(destination, evidence, CaptureState.FAILED, error)
        raise
