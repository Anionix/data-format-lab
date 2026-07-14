import json
from pathlib import Path

import pytest

from format_bench import cli
from format_bench.formats.text import CsvAdapter, ObjectJsonlAdapter
from format_bench.workflow import prepare_run, verify_run


DATASET = "github-stars-2026-07-03"


def test_prepare_and_verify_fixture_record_relative_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    chosen = (CsvAdapter(), ObjectJsonlAdapter())
    prepared = prepare_run(root, DATASET, run_dir, fixture=True, selected=chosen)

    manifest = json.loads((prepared / "manifest.json").read_text())
    assert manifest["state"] == "ENCODED"
    assert manifest["fixture"] is True
    assert manifest["rankable"] is False
    assert all(not Path(entry["artifact"]).is_absolute() for entry in manifest["formats"])
    assert {entry["state"] for entry in manifest["formats"]} == {"ENCODED"}

    verify_run(prepared, {adapter.describe().name: adapter for adapter in chosen})
    verified = json.loads((prepared / "manifest.json").read_text())
    assert verified["state"] == "ROUNDTRIP_VERIFIED"
    assert {entry["state"] for entry in verified["formats"]} == {
        "ROUNDTRIP_VERIFIED"
    }
    assert all(entry["verification"]["passed"] for entry in verified["formats"])


def test_prepare_validates_dataset_before_creating_destination(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"

    with pytest.raises(ValueError, match="one path segment"):
        prepare_run(tmp_path, "../outside", run_dir, fixture=True)

    assert not run_dir.exists()


def test_cli_run_prepares_and_verifies_new_explicit_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).parents[1]
    run_dir = tmp_path / "run"
    calls: list[tuple[str, Path]] = []

    def prepare(
        root: Path, dataset: str, destination: Path, *, fixture: bool
    ) -> Path:
        assert dataset == DATASET
        assert fixture is True
        destination.mkdir()
        calls.append(("prepare", destination))
        return destination

    monkeypatch.setattr(cli, "prepare_run", prepare)
    monkeypatch.setattr(cli, "verify_run", lambda path: calls.append(("verify", path)))
    monkeypatch.setattr(
        cli, "run_prompt", lambda root, path: calls.append(("run", path)) or path
    )
    monkeypatch.chdir(root)

    cli.main(
        [
            "run",
            "--profile",
            "prompt",
            "--dataset",
            DATASET,
            "--run-dir",
            str(run_dir),
            "--fixture",
        ]
    )

    assert calls == [("prepare", run_dir), ("verify", run_dir), ("run", run_dir)]
