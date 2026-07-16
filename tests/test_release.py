import hashlib
import json
import stat
import tarfile
from pathlib import Path

import pytest
import zstandard as zstd

from format_bench.release import package_run


def _archive_names(path: Path) -> list[str]:
    with (
        path.open("rb") as source,
        zstd.ZstdDecompressor().stream_reader(source) as reader,
        tarfile.open(fileobj=reader, mode="r|") as archive,
    ):
        return archive.getnames()


def _robustness_run(root: Path) -> Path:
    run = root / "run"
    case = run / "robustness" / "cases" / "csv" / "rows-1"
    case.mkdir(parents=True)
    (run / "input").mkdir()
    for name in (
        "input.arrow",
        "artifact.csv",
        "stdout.txt",
        "stderr.txt",
        "source.csv",
        "request.json",
        "result.json",
    ):
        (case / name).write_bytes(name.encode())
    manifest = {"state": "REPORTED", "dataset_id": "fixture"}
    results = {
        "state": "REPORTED",
        "dataset_id": "fixture",
        "profile": "robustness",
        "run_id": "run-1",
        "results": {
            "robustness_v1": {
                "cases": [
                    {
                        "input_arrow": {
                            "path": "robustness/cases/csv/rows-1/input.arrow"
                        },
                        "stdout": "robustness/cases/csv/rows-1/stdout.txt",
                        "stderr": "robustness/cases/csv/rows-1/stderr.txt",
                        "artifact_records": [
                            {
                                "path": "robustness/cases/csv/rows-1/artifact.csv"
                            }
                        ],
                        "corpus_records": [
                            {
                                "path": "robustness/cases/csv/rows-1/source.csv"
                            }
                        ],
                    }
                ]
            }
        },
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "results.json").write_text(json.dumps(results))
    (run / "report.md").write_text("# report\n")
    (run / "input" / "manifest.json").write_text('{"dataset_id":"fixture"}\n')
    return run


def test_release_package_is_deterministic_and_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    (run / "input").mkdir(parents=True)
    manifest = {
        "state": "REPORTED",
        "dataset_id": "fixture",
        "formats": [{"artifact": "artifacts/value.bin"}],
    }
    results = {
        "state": "REPORTED",
        "dataset_id": "fixture",
        "profile": "fair",
        "run_id": "run-1",
        "results": {
            "negative_research": {
                "source_commits": {"artifact": "not-a-run-path"}
            }
        },
    }
    payloads = {
        "manifest.json": json.dumps(manifest),
        "results.json": json.dumps(results),
        "report.md": "# report\n",
        "input/manifest.json": '{"dataset_id":"fixture"}\n',
    }
    for relative, payload in payloads.items():
        (run / relative).write_text(payload)
    (run / "artifacts").mkdir()
    (run / "artifacts" / "value.bin").write_bytes(b"artifact")
    (run / "claims" / "nested").mkdir(parents=True)
    (run / "claims" / "nested" / "evidence.bin").write_bytes(b"claim")

    first = package_run(run, tmp_path / "first", "linux-x86_64")
    second = package_run(run, tmp_path / "second", "linux-x86_64")
    assert first.read_bytes() == second.read_bytes()
    assert stat.S_IMODE(first.stat().st_mode) == 0o644
    monkeypatch.chdir(tmp_path)
    relative = package_run(Path("run"), Path("relative"), "linux-x86_64")
    assert first.read_bytes() == relative.read_bytes()
    digest = hashlib.sha256(first.read_bytes()).hexdigest()
    assert first.with_suffix(".zst.sha256").read_text() == f"{digest}  {first.name}\n"

    names = _archive_names(first)
    assert names == [
        "run-1/artifacts/value.bin",
        "run-1/claims/nested/evidence.bin",
        "run-1/input/manifest.json",
        "run-1/manifest.json",
        "run-1/report.md",
        "run-1/results.json",
    ]
    assert all(not Path(name).is_absolute() for name in names)


def test_release_rejects_missing_corpus_record(tmp_path: Path) -> None:
    run = _robustness_run(tmp_path)
    (run / "robustness/cases/csv/rows-1/source.csv").unlink()

    with pytest.raises(FileNotFoundError, match="source.csv"):
        package_run(run, tmp_path / "out", "linux-x86_64")


def test_release_packages_corpus_record(tmp_path: Path) -> None:
    run = _robustness_run(tmp_path)

    archive = package_run(run, tmp_path / "out", "linux-x86_64")

    assert "run-1/robustness/cases/csv/rows-1/source.csv" in _archive_names(archive)


def test_release_rejects_missing_referenced_artifact(tmp_path: Path) -> None:
    run = tmp_path / "run"
    (run / "input").mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "state": "REPORTED",
                "dataset_id": "fixture",
                "formats": [
                    {"artifact": "artifacts/missing.bin", "state": "BENCHMARKED"}
                ],
            }
        )
    )
    (run / "results.json").write_text(
        json.dumps(
            {
                "state": "REPORTED",
                "dataset_id": "fixture",
                "profile": "fair",
                "run_id": "run-1",
            }
        )
    )
    (run / "report.md").write_text("# report\n")
    (run / "input" / "manifest.json").write_text('{}\n')

    try:
        package_run(run, tmp_path / "output", "linux-x86_64")
    except FileNotFoundError as error:
        assert "artifacts/missing.bin" in str(error)
    else:
        raise AssertionError("missing artifact was accepted")


@pytest.mark.parametrize("state", ["FAILED", "UNSUPPORTED"])
def test_release_allows_missing_terminal_format_artifact(
    tmp_path: Path, state: str
) -> None:
    run = tmp_path / state.lower()
    (run / "input").mkdir(parents=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "state": "REPORTED",
                "dataset_id": "fixture",
                "formats": [{"artifact": "artifacts/missing.bin", "state": state}],
            }
        )
    )
    (run / "results.json").write_text(
        json.dumps(
            {
                "state": "REPORTED",
                "dataset_id": "fixture",
                "profile": "fair",
                "run_id": state.lower(),
            }
        )
    )
    (run / "report.md").write_text("# report\n")
    (run / "input" / "manifest.json").write_text('{}\n')

    archive = package_run(run, tmp_path / "output", "linux-x86_64")

    assert archive.is_file()


def test_release_streams_all_robustness_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _robustness_run(tmp_path)
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: (_ for _ in ()).throw(AssertionError(f"read_bytes: {self}")),
    )

    archive = package_run(run, tmp_path / "output", "linux-x86_64")

    assert _archive_names(archive) == [
        "run-1/input/manifest.json",
        "run-1/manifest.json",
        "run-1/report.md",
        "run-1/results.json",
        "run-1/robustness/cases/csv/rows-1/artifact.csv",
        "run-1/robustness/cases/csv/rows-1/input.arrow",
        "run-1/robustness/cases/csv/rows-1/request.json",
        "run-1/robustness/cases/csv/rows-1/result.json",
        "run-1/robustness/cases/csv/rows-1/source.csv",
        "run-1/robustness/cases/csv/rows-1/stderr.txt",
        "run-1/robustness/cases/csv/rows-1/stdout.txt",
    ]


def test_release_rejects_missing_robustness_reference(tmp_path: Path) -> None:
    run = _robustness_run(tmp_path)
    missing = run / "robustness" / "cases" / "csv" / "rows-1" / "input.arrow"
    missing.unlink()

    with pytest.raises(FileNotFoundError, match="input.arrow"):
        package_run(run, tmp_path / "output", "linux-x86_64")


@pytest.mark.parametrize("value", ["/tmp/outside", "../outside"])
def test_release_rejects_unsafe_robustness_reference(
    tmp_path: Path, value: str
) -> None:
    run = _robustness_run(tmp_path)
    results_path = run / "results.json"
    results = json.loads(results_path.read_text())
    results["results"]["robustness_v1"]["cases"][0]["stdout"] = value
    results_path.write_text(json.dumps(results))

    with pytest.raises(ValueError, match="unsafe"):
        package_run(run, tmp_path / "output", "linux-x86_64")


def test_release_rejects_symlinks_in_evidence_roots(tmp_path: Path) -> None:
    run = _robustness_run(tmp_path)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    (run / "robustness" / "linked.bin").symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        package_run(run, tmp_path / "output", "linux-x86_64")
