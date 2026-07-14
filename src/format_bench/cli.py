from __future__ import annotations

import argparse
from pathlib import Path

from .datasets import capture_github_stars, fetch_dataset
from .fair_run import run_fair
from .profile_run import run_claims, run_prompt
from .report import render_report
from .workflow import prepare_run, verify_run


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
    run.add_argument("--profile", choices=["fair", "claims", "prompt"], required=True)
    run.add_argument("--dataset", required=True)
    run.add_argument("--run-dir", type=Path)
    run.add_argument("--fixture", action="store_true")

    report = subcommands.add_parser("report")
    report.add_argument("--run-dir", type=Path, required=True)
    return parser


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
        if args.run_dir is not None and args.fixture:
            raise ValueError("--fixture cannot be combined with --run-dir")
        run_dir = args.run_dir or prepare_run(root, args.dataset, fixture=args.fixture)
        if args.run_dir is None:
            verify_run(run_dir)
        runners = {"fair": run_fair, "claims": run_claims, "prompt": run_prompt}
        path = runners[args.profile](root, run_dir)
    else:
        path = render_report(args.run_dir)
    print(path)
