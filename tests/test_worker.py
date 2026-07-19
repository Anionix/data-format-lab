from pathlib import Path

import pyarrow as pa
import pytest

import format_bench.worker as worker
from format_bench.formats.text import CsvAdapter
from format_bench.workflow import prepare_run, verify_run


class ReorderedScanAdapter(CsvAdapter):
    def __init__(self, *, mutate_after: int | None = None) -> None:
        self.scan_count = 0
        self.mutate_after = mutate_after

    def scan(self, path: Path, manifest: dict, operation):
        table = super().scan(path, manifest, operation)
        self.scan_count += 1
        if self.scan_count > 1:
            table = table.take(pa.array(range(table.num_rows - 1, -1, -1)))
        if self.mutate_after is not None and self.scan_count >= self.mutate_after:
            index = table.schema.get_field_index("repo_stars")
            values = [value + 1 for value in table["repo_stars"].to_pylist()]
            table = table.set_column(
                index,
                table.schema.field(index),
                pa.array(values, type=table.schema.field(index).type),
            )
        return table


def _prepare_csv_run(tmp_path: Path, adapter: ReorderedScanAdapter) -> Path:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    prepare_run(
        root,
        "github-stars-2026-07-03",
        run_dir,
        fixture=True,
        selected=[adapter],
    )
    verify_run(run_dir, {"csv": adapter})
    return run_dir


def test_worker_accepts_reordered_results_on_later_scans(tmp_path, monkeypatch) -> None:
    adapter = ReorderedScanAdapter()
    run_dir = _prepare_csv_run(tmp_path, adapter)
    monkeypatch.setattr(worker, "adapter_map", lambda: {"csv": adapter})
    monkeypatch.setenv("FORMAT_BENCH_WARMUPS", "1")
    monkeypatch.setenv("FORMAT_BENCH_ITERATIONS", "1")

    result = worker.run_fair_worker(run_dir, "csv", "read_all")

    assert result["result"] == 4
    assert adapter.scan_count == 3


def test_worker_rejects_changed_normalized_evidence_on_later_scan(
    tmp_path, monkeypatch
) -> None:
    adapter = ReorderedScanAdapter(mutate_after=3)
    run_dir = _prepare_csv_run(tmp_path, adapter)
    monkeypatch.setattr(worker, "adapter_map", lambda: {"csv": adapter})
    monkeypatch.setenv("FORMAT_BENCH_WARMUPS", "1")
    monkeypatch.setenv("FORMAT_BENCH_ITERATIONS", "1")

    with pytest.raises(ValueError, match="normalized operation result mismatch"):
        worker.run_fair_worker(run_dir, "csv", "read_all")
