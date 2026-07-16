from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from format_bench.model import (
    ExecutionState,
    Lane,
    ObservedOutcome,
    RobustnessExpectation,
    RobustnessVerdict,
    TargetTier,
    robustness_verdict,
)
from format_bench.profile_run import _finish, _load
from format_bench.robustness.evidence import ArtifactBudgetExceeded, EvidenceStore
from format_bench.robustness.runner import _process

ARROW_SOURCE_COMMIT = "7932e197eaa00577ff3e83ddf956022df3ef174c"
VORTEX_SOURCE_COMMIT = "5abaf9823dee973dde7295a6a36234935f08d060"
FASTLANES_SOURCE_COMMIT = "f0edc1020a538f1f8098640fce8347c9ac247a0d"
DEFAULT_NATIVE_BUILD_DIR = Path("native/arrow/build")
_NATIVE_OUTPUT_BUDGET_BYTES = 1024 * 1024
_FASTLANES_BUILD_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class NativeTarget:
    name: str
    official_target: str
    engine: str
    work_dir: Path
    binary_name: str | None = None
    tier: TargetTier = TargetTier.EXPERIMENTAL
    source_commit: str | None = None


ARROW_NATIVE_TARGETS: tuple[NativeTarget, ...] = tuple(
    NativeTarget(
        name,
        name,
        "coverage-guided",
        Path("native/arrow"),
        name,
        TargetTier.CORE,
        ARROW_SOURCE_COMMIT,
    )
    for name in ("arrow-csv-fuzz", "parquet-arrow-fuzz", "parquet-encoding-fuzz")
)
VORTEX_NATIVE_TARGETS = (
    NativeTarget(
        "vortex-file-io",
        "file_io",
        "coverage-guided",
        Path("native/vortex"),
        tier=TargetTier.CORE,
        source_commit=VORTEX_SOURCE_COMMIT,
    ),
    NativeTarget(
        "vortex-compress-roundtrip",
        "compress_roundtrip",
        "coverage-guided",
        Path("native/vortex"),
        tier=TargetTier.CORE,
        source_commit=VORTEX_SOURCE_COMMIT,
    ),
)
FASTLANES_NATIVE_TARGETS = (
    NativeTarget(
        "fastlanes-quick-fuzz",
        "quick_fuzz_test",
        "project-seeded",
        Path("native/fastlanes"),
        "quick_fuzz_test",
        TargetTier.EXPERIMENTAL,
        FASTLANES_SOURCE_COMMIT,
    ),
)
UNAVAILABLE_NATIVE_TARGETS = (
    NativeTarget("lance", "", "unavailable", Path("native/lance")),
    NativeTarget("object-jsonl", "", "unavailable", Path("native/object-jsonl")),
    NativeTarget("tsfile", "", "unavailable", Path("native/tsfile")),
)
NATIVE_TARGETS = (
    ARROW_NATIVE_TARGETS
    + VORTEX_NATIVE_TARGETS
    + FASTLANES_NATIVE_TARGETS
    + UNAVAILABLE_NATIVE_TARGETS
)


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _fuzz_seconds(duration_seconds: float) -> int:
    return max(1, math.ceil(duration_seconds))


def _binary(build_dir: Path, target: NativeTarget) -> Path | None:
    if target.binary_name is None:
        return None
    if build_dir.is_symlink():
        return None
    build_root = build_dir.resolve()
    candidates = [build_dir / target.binary_name]
    if build_dir.is_dir():
        candidates.extend(sorted(build_dir.rglob(target.binary_name)))
    return next(
        (
            path
            for path in candidates
            if not path.is_symlink()
            and path.is_file()
            and os.access(path, os.X_OK)
            and path.resolve().is_relative_to(build_root)
        ),
        None,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit_error(root: Path, target: NativeTarget) -> str | None:
    if target.source_commit is None:
        return None
    source_root = root / target.work_dir
    if not (source_root / ".git").exists():
        return f"source checkout for {target.name} has no .git metadata"
    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"could not read source commit: {type(error).__name__}: {error}"
    actual = completed.stdout.strip()
    if completed.returncode != 0 or actual != target.source_commit:
        return f"source commit mismatch: expected {target.source_commit}, got {actual or 'unknown'}"
    try:
        status = subprocess.run(
            ["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=no"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"could not inspect source checkout: {type(error).__name__}: {error}"
    if status.returncode != 0:
        return f"could not inspect source checkout: exit {status.returncode}"
    if status.stdout.strip():
        return f"source checkout for {target.name} has tracked changes"
    return None


def _refresh_fastlanes(root: Path, target: NativeTarget) -> str | None:
    if target.name != "fastlanes-quick-fuzz" or target.source_commit is None:
        return None
    source_root = root / target.work_dir
    build_dir = source_root / "build"
    if not (build_dir / "CMakeCache.txt").is_file():
        return "FastLanes build directory is not configured"
    try:
        completed = subprocess.run(
            [
                "cmake",
                "--build",
                str(build_dir),
                "--target",
                target.binary_name or "",
                "--clean-first",
            ],
            cwd=source_root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_FASTLANES_BUILD_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"could not rebuild FastLanes target: {type(error).__name__}: {error}"
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()[-1024:]
        return f"FastLanes rebuild failed: {stderr or f'exit {completed.returncode}'}"
    return None


def _corpus_source(run_dir: Path, run: dict, target: NativeTarget) -> Path:
    run_root = run_dir.resolve()
    if target.name != "arrow-csv-fuzz":
        for entry in run["formats"]:
            if entry["format"] == "parquet_default" and entry["state"] == ExecutionState.ROUNDTRIP_VERIFIED:
                return _safe_run_file(run_root, entry["artifact"], "native corpus")
    return _safe_run_file(run_root, run["input"]["source"], "native corpus")


def _copy_corpus_seed(
    run_dir: Path, run: dict, target: NativeTarget, destination: Path
) -> tuple[Path, Path]:
    # Resolve and isolate the seed before _process changes the child's cwd.
    # libFuzzer writes new units into its corpus directory, so never hand it a
    # shared run directory managed by the evidence store.
    source = _corpus_source(run_dir, run, target)
    destination.mkdir()
    shutil.copy2(source, destination / source.name)
    return source, destination


def _safe_run_file(run_root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"{label} path must be a string")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError(f"{label} path must be safe and relative")
    candidate = run_root / relative
    if any(item.is_symlink() for item in (candidate, *candidate.parents) if item != run_root.parent):
        raise ValueError(f"{label} path must not contain symlinks")
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(run_root) or not resolved.is_file():
        raise ValueError(f"{label} path must exist inside the run directory")
    return resolved


def _base(target: NativeTarget) -> dict[str, object]:
    return {
        "schema_version": "1",
        "contract_version": "1",
        "case_id": f"native-{target.name}",
        "target": target.name,
        "tier": target.tier,
        "expectation": RobustnessExpectation.MUST_NOT_CRASH,
    }


def _case(
    target: NativeTarget,
    run_dir: Path,
    store: EvidenceStore,
    duration_seconds: float,
    fixture: bool,
    run: dict,
    build_dir: Path,
    root: Path,
) -> dict[str, object]:
    base = _base(target)
    if target.engine == "unavailable":
        return {
            **base,
            "observed": ObservedOutcome.UNSUPPORTED,
            "verdict": RobustnessVerdict.INCOMPLETE,
            "details": {
                "reason": "no confirmed official native fuzz target",
                "official_target": None,
                "engine": target.engine,
            },
        }
    source_error = _source_commit_error(root, target)
    if source_error is not None:
        return {
            **base,
            "observed": ObservedOutcome.UNSUPPORTED,
            "verdict": RobustnessVerdict.INCOMPLETE,
            "details": {
                "reason": source_error,
                "official_target": target.official_target,
                "engine": target.engine,
                "source_commit": target.source_commit,
            },
        }
    build_error = _refresh_fastlanes(root, target)
    if build_error is not None:
        return {
            **base,
            "observed": ObservedOutcome.HARNESS_FAILED,
            "verdict": RobustnessVerdict.INCOMPLETE,
            "details": {
                "reason": build_error,
                "official_target": target.official_target,
                "engine": target.engine,
                "source_commit": target.source_commit,
            },
        }
    run_root = run_dir.resolve()
    binary_root = build_dir if target.name in {item.name for item in ARROW_NATIVE_TARGETS} else root / target.work_dir / "build"
    binary = _binary(binary_root, target)
    work_dir = root / target.work_dir
    if target.name in {item.name for item in ARROW_NATIVE_TARGETS} and build_dir is not None:
        work_dir = build_dir
    if not work_dir.is_dir() or (target.binary_name is not None and binary is None):
        return {
            **base,
            "observed": ObservedOutcome.UNSUPPORTED,
            "verdict": RobustnessVerdict.INCOMPLETE,
            "details": {
                "reason": "official native target is unavailable",
                "official_target": target.official_target,
                "engine": target.engine,
                "source_commit": target.source_commit,
            },
        }
    prefix = Path("native") / target.name
    with tempfile.TemporaryDirectory(dir=run_root) as temporary:
        artifacts = Path(temporary) / "artifacts"
        artifacts.mkdir()
        corpus_source: Path | None = None
        corpus: Path | None = None
        try:
            corpus_source, corpus = (
                _copy_corpus_seed(run_dir, run, target, Path(temporary) / "corpus")
                if target.engine == "coverage-guided" and target.binary_name
                else (None, None)
            )
        except (OSError, ValueError) as error:
            return {
                **base,
                "observed": ObservedOutcome.HARNESS_FAILED,
                "verdict": RobustnessVerdict.INCOMPLETE,
                "details": {"reason": str(error)},
            }
        limits = [
            f"-max_total_time={_fuzz_seconds(duration_seconds)}",
            f"-artifact_prefix={artifacts.as_posix()}/",
        ]
        if target.engine == "coverage-guided" and target.binary_name is None:
            command = ["cargo", "fuzz", "run", target.official_target, "--", *limits]
        elif target.engine == "coverage-guided":
            assert corpus is not None
            command = [
                str(binary), "-print_final_stats=1",
                f"-timeout={_fuzz_seconds(duration_seconds)}",
                *limits,
            ]
        else:
            command = [
                str(binary),
                "--gtest_filter=QuickFuzz_*",
                "--gtest_color=no",
                f"--gtest_output=xml:{artifacts / 'gtest.xml'}",
            ]
        if target.engine == "coverage-guided" and fixture:
            command.append("-runs=1")
        if corpus is not None:
            command.append(corpus.as_posix())
        process, stdout, stderr = _process(
            command, work_dir, duration_seconds + 5, output_budget_bytes=_NATIVE_OUTPUT_BUDGET_BYTES
        )
        if process["timed_out"]:
            observed = ObservedOutcome.TIMED_OUT
        elif process["signal"] is not None:
            observed = ObservedOutcome.CRASHED
        elif process["exit_code"] == 0:
            observed = ObservedOutcome.ACCEPTED
        elif target.engine == "project-seeded":
            observed = ObservedOutcome.TARGET_FAILED
        else:
            observed = ObservedOutcome.HARNESS_FAILED
        details: dict[str, object] = {
            "official_target": target.official_target,
            "engine": target.engine,
            "source_commit": target.source_commit,
        }
        if binary is not None:
            details["binary_sha256"] = _sha256(binary)
        if corpus_source is not None:
            details["corpus"] = corpus_source.relative_to(run_root).parent.as_posix()
            details["corpus_isolated"] = True
        result = {
            **base,
            "observed": observed,
            "verdict": robustness_verdict(RobustnessExpectation.MUST_NOT_CRASH, observed),
            "details": details,
            "process": process,
        }
        try:
            records = store.import_path(artifacts, prefix / "artifacts")
            stdout_record = store.store_bytes(prefix / "stdout.txt", stdout.encode())
            stderr_record = store.store_bytes(prefix / "stderr.txt", stderr.encode())
            result.update(
                stdout=f"robustness/{stdout_record.relative_path}",
                stderr=f"robustness/{stderr_record.relative_path}",
                artifact_records=[
                    {"path": f"robustness/{record.relative_path}", "size_bytes": record.size_bytes, "sha256": record.sha256}
                    for record in records
                ],
            )
            store.store_bytes(prefix / "result.json", _json(result))
        except ArtifactBudgetExceeded as error:
            return {
                **base,
                "observed": ObservedOutcome.BUDGET_EXHAUSTED,
                "verdict": RobustnessVerdict.INCOMPLETE,
                "details": {"error_type": type(error).__name__, "message": str(error)},
            }
        return result


def run_native(
    root: Path,
    run_dir: Path,
    *,
    duration_seconds: float = 900.0,
    artifact_budget_mib: int = 1024,
    targets: tuple[NativeTarget, ...] | None = None,
    build_dir: Path | None = None,
) -> Path:
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("duration_seconds must be a finite positive number")
    if artifact_budget_mib <= 0:
        raise ValueError("artifact_budget_mib must be positive")
    run, _ = _load(run_dir)
    effective_build_dir = build_dir or root / DEFAULT_NATIVE_BUILD_DIR
    store = EvidenceStore(run_dir / "robustness", artifact_budget_mib * 1024 * 1024)
    selected = targets or NATIVE_TARGETS
    observations = [
        _case(target, run_dir, store, duration_seconds, bool(run["fixture"]), run, effective_build_dir, root)
        for target in selected
    ]
    summary = {verdict.value: 0 for verdict in RobustnessVerdict}
    for item in observations:
        summary[str(item["verdict"])] += 1
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    # Native failures remain UNSUPPORTED or FAILED evidence and never rank.
    evidence = {
        "robustness_v1": {
            "contract_version": "1",
            "state": ExecutionState.BENCHMARKED,
            "suite": "native",
            "config": {
                "seed": run["seed"],
                "generated_cases": 0,
                "mutations_per_target": 0,
                "case_timeout_seconds": duration_seconds + 5,
                "artifact_budget_mib": artifact_budget_mib,
                "duration_seconds": duration_seconds,
                "source_commits": {
                    "arrow": ARROW_SOURCE_COMMIT,
                    "vortex": VORTEX_SOURCE_COMMIT,
                    "fastlanes": FASTLANES_SOURCE_COMMIT,
                },
                "build_dir": effective_build_dir.relative_to(root).as_posix()
                if effective_build_dir.is_relative_to(root)
                else DEFAULT_NATIVE_BUILD_DIR.as_posix(),
            },
            "cases": observations,
            "summary": summary,
        }
    }
    return _finish(root, run_dir, run, Lane.ROBUSTNESS, evidence)
