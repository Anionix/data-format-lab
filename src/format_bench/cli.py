from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import TypeVar

from .datasets import capture_github_stars, fetch_dataset, load_manifest
from .fair_run import run_fair
from .profile_run import run_claims, run_prompt
from .release import package_run
from .report import render_report
from .robustness.profile import run_bounded
from .robustness.native import NATIVE_TARGETS, run_native
from .workflow import prepare_run, verify_run


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
    capture.add_argument("source", choices=["github-stars"])
    capture.add_argument("--user", required=True)
    capture.add_argument("--output", type=Path, default=Path(".data/captures"))

    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--dataset", required=True)
    prepare.add_argument("--run-dir", type=Path)
    prepare.add_argument("--fixture", action="store_true")

    verify = subcommands.add_parser("verify")
    verify.add_argument("--run-dir", type=Path, required=True)

    run = subcommands.add_parser("run")
    run.add_argument(
        "--profile", choices=["fair", "claims", "prompt", "robustness"], required=True
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

    report = subcommands.add_parser("report")
    report.add_argument("--run-dir", type=Path, required=True)

    package = subcommands.add_parser("package")
    package.add_argument("--run-dir", type=Path, required=True)
    package.add_argument("--output", type=Path, default=Path("outputs/release"))
    package.add_argument("--platform", required=True)
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
    )
    if args.profile != "robustness":
        if any(value is not None for value in robustness_options):
            raise ValueError(
                "robustness options only apply with --profile robustness"
            )
        return
    if args.suite not in {"bounded", "native"}:
        raise ValueError("--profile robustness requires --suite bounded or native")
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


def _run_directory(root: Path, args: argparse.Namespace) -> Path:
    load_manifest(root, args.dataset)
    if args.run_dir is None or not args.run_dir.exists():
        run_dir = prepare_run(
            root, args.dataset, args.run_dir, fixture=args.fixture
        )
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
    args = build_parser().parse_args(argv)
    root = Path.cwd()
    if args.command == "dataset":
        if args.dataset_command == "fetch":
            path = fetch_dataset(root, args.dataset_id, args.output)
        else:
            path = capture_github_stars(args.user, args.output)
    elif args.command == "prepare":
        path = prepare_run(root, args.dataset, args.run_dir, fixture=args.fixture)
    elif args.command == "verify":
        path = verify_run(args.run_dir)
    elif args.command == "run":
        _validate_run_options(args)
        run_dir = _run_directory(root, args)
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
            runners = {"fair": run_fair, "claims": run_claims, "prompt": run_prompt}
            path = runners[args.profile](root, run_dir)
    elif args.command == "report":
        path = render_report(args.run_dir)
    else:
        path = package_run(args.run_dir, args.output, args.platform)
    print(path)
