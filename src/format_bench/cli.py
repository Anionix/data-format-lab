from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from .canonical import load_dataset, read_csv
from .datasets import capture_github_stars, capture_nyc_snapshot, fetch_dataset, load_manifest
from .equivalence_run import PAIR_SPECS, run_equivalence
from .fair_run import run_fair
from .implementation_audit import EXPECTED_ADAPTER_LANES, audit_implementation
from .model import ExecutionState
from .profile_run import run_claims, run_prompt
from .release import package_run
from .report import render_report
from .robustness.profile import run_bounded
from .robustness.native import NATIVE_TARGETS, run_native
from .interop import run_arrow_ipc_interoperability
from .runner import MeasurementConfig, environment_info
from .shards import merge_equivalence_shards
from .workflow import _fixture_manifest, prepare_run, verify_run
from .workloads import load_workloads
from .registry import adapter_map, adapters


_T = TypeVar("_T")


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="format-bench")
    subcommands = parser.add_subparsers(dest="command", required=True)
    dataset = subcommands.add_parser("dataset")
    actions = dataset.add_subparsers(dest="dataset_command", required=True)

    fetch = actions.add_parser("fetch")
    fetch.add_argument("dataset_id")
    fetch.add_argument("--output", type=Path)

    capture = actions.add_parser("capture")
    capture.add_argument("source", choices=["github-stars", "nyc-311-2010-2019"])
    capture.add_argument("--user")
    capture.add_argument("--output", type=Path)

    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--dataset", required=True)
    prepare.add_argument("--run-dir", type=Path)
    prepare.add_argument("--fixture", action="store_true")

    verify = subcommands.add_parser("verify")
    verify.add_argument("--run-dir", type=Path, required=True)

    run = subcommands.add_parser("run")
    run.add_argument(
        "--profile",
        choices=["fair", "claims", "prompt", "robustness", "equivalence"],
        required=True,
    )
    run.add_argument("--dataset", required=True)
    run.add_argument("--run-dir", type=Path)
    run.add_argument("--fixture", action="store_true")
    run.add_argument("--suite", choices=["bounded", "native"])
    run.add_argument("--target", action="append")
    run.add_argument("--duration-seconds", type=_positive_float)
    run.add_argument("--seed", type=int)
    run.add_argument("--generated-cases", type=_non_negative_int)
    run.add_argument("--mutations-per-target", type=_non_negative_int)
    run.add_argument("--case-timeout-seconds", type=_positive_float)
    run.add_argument("--artifact-budget-mib", type=_positive_int)
    run.add_argument("--pair", action="append", choices=sorted(PAIR_SPECS))
    run.add_argument("--fresh-processes", type=_positive_int)
    run.add_argument("--fresh-workers", type=_positive_int)
    run.add_argument("--warmups", type=_non_negative_int)
    run.add_argument("--iterations", type=_positive_int)
    run.add_argument("--worker-timeout-seconds", type=_positive_float)
    run.add_argument("--parallel-jobs", action="store_true")

    report = subcommands.add_parser("report")
    report.add_argument("--run-dir", type=Path, required=True)

    interop = subcommands.add_parser("interop")
    interop.add_argument("--dataset", required=True)
    interop.add_argument("--output", type=Path)
    interop.add_argument("--fixture", action="store_true")

    package = subcommands.add_parser("package")
    package.add_argument("--run-dir", type=Path, required=True)
    package.add_argument("--output", type=Path, default=Path("outputs/release"))
    package.add_argument("--platform", required=True)
    package.add_argument(
        "--source-root",
        type=Path,
        default=Path("."),
        help="root for aggregate source run paths (default: current directory)",
    )

    merge = subcommands.add_parser("merge-equivalence-shards")
    merge.add_argument("--base-run-dir", type=Path, required=True)
    merge.add_argument("--shard-dir", type=Path, required=True)
    merge.add_argument("--output-run-dir", type=Path, required=True)

    audit = subcommands.add_parser("audit")
    audit.add_argument("--dataset", required=True)
    audit.add_argument("--run-dir", type=Path)
    audit.add_argument("--output", type=Path)
    return parser


def _validate_run_options(args: argparse.Namespace) -> None:
    robustness_options = (
        args.suite,
        args.seed,
        args.generated_cases,
        args.mutations_per_target,
        args.case_timeout_seconds,
        args.artifact_budget_mib,
        args.target,
        args.duration_seconds,
        args.pair,
    )
    measurement_options = (
        args.fresh_processes,
        args.fresh_workers,
        args.warmups,
        args.iterations,
        args.worker_timeout_seconds,
        True if args.parallel_jobs else None,
    )
    if args.profile not in {"fair", "equivalence"} and any(
        value is not None for value in measurement_options
    ):
        raise ValueError("measurement options require --profile fair or equivalence")
    if args.profile == "fair" and args.parallel_jobs:
        raise ValueError("--parallel-jobs requires --profile equivalence")
    if args.profile not in {"robustness", "equivalence"}:
        if any(value is not None for value in robustness_options):
            raise ValueError(
                "robustness and equivalence options only apply to their matching profile"
            )
        return
    if args.profile == "equivalence":
        if any(
            value is not None
            for value in (
                args.suite,
                args.seed,
                args.generated_cases,
                args.mutations_per_target,
                args.case_timeout_seconds,
                args.artifact_budget_mib,
                args.target,
                args.duration_seconds,
            )
        ):
            raise ValueError("robustness options require --profile robustness")
        return
    if args.suite not in {"bounded", "native"}:
        raise ValueError("--profile robustness requires --suite bounded or native")
    if args.pair:
        raise ValueError("--pair requires --profile equivalence")
    if args.suite == "bounded" and (args.target or args.duration_seconds is not None):
        raise ValueError("--target and --duration-seconds require --suite native")
    if args.suite == "native" and any(
        value is not None
        for value in (
            args.seed,
            args.generated_cases,
            args.mutations_per_target,
            args.case_timeout_seconds,
        )
    ):
        raise ValueError("bounded robustness options require --suite bounded")


def _default(value: _T | None, default: _T) -> _T:
    return default if value is None else value


def _measurement_config(args: argparse.Namespace, run_dir: Path) -> MeasurementConfig | None:
    options = (
        args.fresh_processes,
        args.fresh_workers,
        args.warmups,
        args.iterations,
        args.worker_timeout_seconds,
    )
    if not any(value is not None for value in options):
        return None

    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if args.profile == "fair":
        defaults = (
            MeasurementConfig(fresh_processes=1, warmups=0, iterations=1)
            if run_manifest.get("fixture")
            else MeasurementConfig()
        )
    elif args.profile == "equivalence":
        defaults = (
            MeasurementConfig(fresh_processes=2, warmups=1, iterations=2)
            if run_manifest.get("fixture")
            else MeasurementConfig()
        )
    else:
        raise ValueError("measurement options require --profile fair or equivalence")

    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    return MeasurementConfig(
        fresh_processes=_default(args.fresh_processes, defaults.fresh_processes),
        fresh_workers=_default(args.fresh_workers, defaults.fresh_workers),
        warmups=_default(args.warmups, defaults.warmups),
        iterations=_default(args.iterations, defaults.iterations),
        timeout_seconds=_default(args.worker_timeout_seconds, defaults.timeout_seconds),
    )


def _run_directory(root: Path, args: argparse.Namespace) -> Path:
    load_manifest(root, args.dataset)
    if args.run_dir is None or not args.run_dir.exists():
        selected = None
        if args.profile == "equivalence":
            names = {
                name
                for pair in (args.pair or tuple(PAIR_SPECS))
                for name in (
                    PAIR_SPECS[pair]["reference"],
                    *PAIR_SPECS[pair]["candidates"],
                )
            }
            registered = adapter_map()
            selected = tuple(registered[name] for name in sorted(names))
        prepare_kwargs = {"fixture": args.fixture}
        if selected is not None:
            prepare_kwargs["selected"] = selected
        run_dir = prepare_run(root, args.dataset, args.run_dir, **prepare_kwargs)
        verify_run(run_dir)
        return run_dir
    if args.fixture:
        raise ValueError("--fixture only applies when creating a run directory")
    manifest_path = args.run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("existing run directory must contain manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != args.dataset:
        raise ValueError("run directory dataset does not match --dataset")
    return args.run_dir


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd()
    if args.command == "dataset":
        if args.dataset_command == "fetch":
            path = fetch_dataset(root, args.dataset_id, args.output)
        elif args.source == "nyc-311-2010-2019":
            if args.user is not None:
                parser.error("--user only applies to github-stars capture")
            output = args.output or Path(".data/captures") / (
                "nyc-311-2010-2019-"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            )
            path = capture_nyc_snapshot(root, output)
        else:
            if args.user is None:
                parser.error("github-stars capture requires --user")
            path = capture_github_stars(
                args.user, args.output or Path(".data/captures")
            )
    elif args.command == "prepare":
        path = prepare_run(root, args.dataset, args.run_dir, fixture=args.fixture)
    elif args.command == "verify":
        path = verify_run(args.run_dir)
    elif args.command == "run":
        _validate_run_options(args)
        run_dir = _run_directory(root, args)
        measurement = _measurement_config(args, run_dir)
        if args.profile == "robustness":
            if args.suite == "native":
                selected = None
                if args.target:
                    available = {target.name: target for target in NATIVE_TARGETS}
                    unknown = sorted(set(args.target) - available.keys())
                    if unknown:
                        raise ValueError(f"unknown native target: {', '.join(unknown)}")
                    selected = tuple(available[name] for name in args.target)
                path = run_native(
                    root,
                    run_dir,
                    duration_seconds=_default(args.duration_seconds, 900.0),
                    artifact_budget_mib=_default(args.artifact_budget_mib, 1024),
                    targets=selected,
                )
            else:
                path = run_bounded(
                    root,
                    run_dir,
                    seed=_default(args.seed, 20260703),
                    generated_count=_default(args.generated_cases, 32),
                    mutations_per_target=_default(args.mutations_per_target, 64),
                    timeout_seconds=_default(args.case_timeout_seconds, 30.0),
                    artifact_budget_mib=_default(args.artifact_budget_mib, 1024),
                )
        else:
            if args.profile == "equivalence":
                path = run_equivalence(
                    root,
                    run_dir,
                    pairs=tuple(args.pair) if args.pair else None,
                    config=measurement,
                    parallel=args.parallel_jobs,
                )
            else:
                runners = {"fair": run_fair, "claims": run_claims, "prompt": run_prompt}
                path = runners[args.profile](root, run_dir, config=measurement) if measurement else runners[args.profile](root, run_dir)
    elif args.command == "report":
        path = render_report(args.run_dir)
    elif args.command == "interop":
        output = args.output or Path("outputs") / (
            "interop-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        source = (
            root / "datasets" / args.dataset / "fixture.csv"
            if args.fixture
            else root / ".data" / args.dataset / "source.csv"
        )
        if args.fixture:
            manifest = load_manifest(root, args.dataset)
            table = read_csv(source, manifest)
            manifest = _fixture_manifest(manifest, table, source)
        else:
            manifest, table = load_dataset(root, args.dataset, source=source)
        path = run_arrow_ipc_interoperability(
            table, manifest, output, environment=environment_info(root)
        )
    elif args.command == "audit":
        dataset_manifest = load_manifest(root, args.dataset)
        run_manifest = (
            json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
            if args.run_dir is not None
            else None
        )
        artifact_paths = (
            [entry["artifact"] for entry in run_manifest["formats"]]
            if run_manifest is not None
            else [
                "artifacts/" + adapter.describe().name + adapter.describe().extension
                for adapter in adapters()
            ]
        )
        evidence = audit_implementation(
            adapters(),
            lifecycle=(
                ExecutionState.DISCOVERED,
                ExecutionState.ENCODED,
                ExecutionState.ROUNDTRIP_VERIFIED,
                ExecutionState.BENCHMARKED,
                ExecutionState.REPORTED,
            ),
            artifact_paths=artifact_paths,
            workloads=load_workloads(dataset_manifest),
            required_operations=load_workloads(dataset_manifest),
            expected_adapter_count=len(EXPECTED_ADAPTER_LANES),
            expected_lanes=EXPECTED_ADAPTER_LANES,
            path_root=args.run_dir,
        )
        payload = {
            "schema_version": "1",
            "dataset_id": args.dataset,
            "audit": evidence.as_dict(),
        }
        output = args.output or (
            args.run_dir / "implementation-audit.json"
            if args.run_dir is not None
            else Path("outputs") / f"implementation-audit-{args.dataset}.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        path = output
    elif args.command == "merge-equivalence-shards":
        path = merge_equivalence_shards(
            args.base_run_dir, args.shard_dir, args.output_run_dir
        )
    else:
        path = package_run(
            args.run_dir,
            args.output,
            args.platform,
            source_root=args.source_root,
        )
    print(path)
