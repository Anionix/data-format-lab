import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from format_bench import dataset_sources, nyc_snapshot
from format_bench.dataset_sources import materialize_official


DATASET = Path("datasets/nyc-311-2010-2019/manifest.json")
HEADER = b":id,unique_key,created_date,complaint_type,borough,complaint_text\n"


def _manifest(target: int) -> dict[str, object]:
    manifest = json.loads(DATASET.read_text())
    source = manifest["source"]
    source["snapshot_rows_target"] = target
    source["future_capture"]["pagination"]["page_size"] = 2
    return manifest


def _metadata(revision: int) -> bytes:
    cursor = {"fieldName": "unique_key", "dataTypeName": "text"}
    return json.dumps({"id": "76ig-c548", "rowsUpdatedAt": revision, "columns": [cursor]}).encode()


def test_nyc_capture_retains_keyset_pages_and_hash_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = HEADER + b"row-nref,10,2010-01-01,A,X,one\nrow-yy9w,20,2010-01-02,B,Y,two\n"
    second = HEADER + b"row-n58n,30,2010-01-03,C,Z,three\n"
    requests: list[dict[str, list[str]]] = []

    def get(url: str, accept: str) -> bytes:
        if url.endswith("/76ig-c548"):
            return _metadata(123)
        query = parse_qs(urlsplit(url).query)
        requests.append(query)
        return first if len(requests) == 1 else second

    monkeypatch.setattr(nyc_snapshot, "_get", get)
    output = tmp_path / "capture"
    manifest = _manifest(3)

    materialize_official("nyc-311-2010-2019", manifest, b"", output)

    assert all("$offset" not in request for request in requests)
    assert requests[1]["$where"][0].endswith(":id > 'row-yy9w'")
    assert (output / "raw-pages/page-00000.csv").read_bytes() == first
    evidence = json.loads((output / "capture.json").read_text())
    assert evidence["status"] == "COMPLETE"
    assert evidence["lifecycle_status"] == "ENCODED"
    assert evidence["raw_pages"][0]["sha256"] == hashlib.sha256(first).hexdigest()
    assert evidence["revision"]["metadata_before_sha256"] == hashlib.sha256(_metadata(123)).hexdigest()
    assert evidence["revision"]["metadata_after_sha256"] == hashlib.sha256(_metadata(123)).hexdigest()
    assert evidence["started_at"] <= evidence["finished_at"]
    source = (output / "source.csv").read_bytes()
    assert source.startswith(b"unique_key,")
    materialization = json.loads((output / "materialization.json").read_text())
    assert materialization["source_sha256"] == hashlib.sha256(source).hexdigest()
    assert materialization["writer"]["encoding"] == "utf-8"
    assert materialization["writer"]["lineterminator"] == "\n"


def test_nyc_capture_fails_closed_on_revision_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = iter((_metadata(123), _metadata(124)))
    page = HEADER + b"row-001,10,2010-01-01,A,X,one\n"

    def get(url: str, accept: str) -> bytes:
        return next(metadata) if url.endswith("/76ig-c548") else page

    monkeypatch.setattr(nyc_snapshot, "_get", get)
    output = tmp_path / "capture"

    with pytest.raises(ValueError, match="revision changed"):
        materialize_official("nyc-311-2010-2019", _manifest(1), b"", output)

    evidence = json.loads((output / "capture.json").read_text())
    assert evidence["status"] == "FAILED"
    assert evidence["lifecycle_status"] == "FAILED"
    assert evidence["failure_reason"].endswith("revision changed during capture")
    assert evidence["revision"]["matched"] is False
    assert not (output / "source.csv").exists()
    assert not (output / "source.csv.partial").exists()
    assert not (output / "materialization.json").exists()


def test_nyc_capture_records_initial_metadata_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nyc_snapshot, "_get", lambda url, accept: (_ for _ in ()).throw(TimeoutError()))
    output = tmp_path / "capture"

    with pytest.raises(TimeoutError):
        materialize_official("nyc-311-2010-2019", _manifest(1), b"", output)

    evidence = json.loads((output / "capture.json").read_text())
    assert evidence["status"] == "FAILED"
    assert evidence["failure_reason"].startswith("TimeoutError:")


def test_nyc_capture_records_received_page_before_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad_page = b":id,wrong\nrow-001,value\n"
    monkeypatch.setattr(
        nyc_snapshot,
        "_get",
        lambda url, accept: _metadata(123) if url.endswith("/76ig-c548") else bad_page,
    )
    output = tmp_path / "capture"

    with pytest.raises(ValueError, match="columns do not match"):
        materialize_official("nyc-311-2010-2019", _manifest(1), b"", output)

    evidence = json.loads((output / "capture.json").read_text())
    assert evidence["raw_pages"][0]["status"] == "RECEIVED"
    assert evidence["raw_pages"][0]["sha256"] == hashlib.sha256(bad_page).hexdigest()


def test_nyc_capture_hashes_malformed_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    malformed = b"not-json"
    monkeypatch.setattr(nyc_snapshot, "_get", lambda url, accept: malformed)
    output = tmp_path / "capture"

    with pytest.raises(json.JSONDecodeError):
        materialize_official("nyc-311-2010-2019", _manifest(1), b"", output)

    evidence = json.loads((output / "capture.json").read_text())
    assert evidence["status"] == "FAILED"
    assert evidence["revision"]["metadata_before_sha256"] == hashlib.sha256(malformed).hexdigest()


def test_nyc_capture_rejects_replayed_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = HEADER + b"row-opaque,10,2010-01-01,A,X,one\nrow-opaque,20,2010-01-02,B,Y,two\n"
    monkeypatch.setattr(
        nyc_snapshot,
        "_get",
        lambda url, accept: _metadata(123) if url.endswith("/76ig-c548") else page,
    )

    with pytest.raises(ValueError, match="cursor repeated"):
        materialize_official("nyc-311-2010-2019", _manifest(2), b"", tmp_path / "capture")


def test_nyc_capture_records_interrupt_and_removes_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        nyc_snapshot,
        "_get",
        lambda url, accept: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    output = tmp_path / "capture"

    with pytest.raises(KeyboardInterrupt):
        materialize_official("nyc-311-2010-2019", _manifest(1), b"", output)

    evidence = json.loads((output / "capture.json").read_text())
    assert evidence["status"] == "FAILED"
    assert evidence["failure_reason"].startswith("KeyboardInterrupt:")
    assert not (output / "source.csv.partial").exists()


def test_nyc_capture_records_consumer_failure_after_yield(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = HEADER + b"row-opaque,10,2010-01-01,A,X,one\n"
    monkeypatch.setattr(
        nyc_snapshot,
        "_get",
        lambda url, accept: _metadata(123) if url.endswith("/76ig-c548") else page,
    )

    def fail_after_row(
        destination: Path,
        manifest: Mapping[str, object],
        rows: Iterable[Mapping[str, object]],
    ) -> int:
        next(iter(rows))
        raise OSError("write failed")

    monkeypatch.setattr(dataset_sources, "_write_rows", fail_after_row)
    output = tmp_path / "capture"
    with pytest.raises(OSError, match="write failed"):
        materialize_official("nyc-311-2010-2019", _manifest(1), b"", output)

    evidence = json.loads((output / "capture.json").read_text())
    assert evidence["status"] == "FAILED"
    assert evidence["lifecycle_status"] == "FAILED"
    assert evidence["failure_reason"].endswith("write failed")
    assert evidence["revision"]["before"] == "123"
    assert evidence["revision"]["metadata_before_sha256"] == hashlib.sha256(
        _metadata(123)
    ).hexdigest()
    assert evidence["raw_pages"][0]["status"] == "VALIDATED"
    assert evidence["raw_pages"][0]["sha256"] == hashlib.sha256(page).hexdigest()
    assert evidence["raw_pages"][0]["first_cursor"] == "row-opaque"
    assert evidence["raw_pages"][0]["last_cursor"] == "row-opaque"
    assert evidence["revision"]["after"] is None
    assert evidence["revision"]["matched"] is False
    assert (output / evidence["raw_pages"][0]["path"]).read_bytes() == page
    assert not (output / "source.csv.partial").exists()
