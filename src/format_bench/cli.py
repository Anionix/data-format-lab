from __future__ import annotations

import argparse
from pathlib import Path

from .datasets import capture_github_stars, fetch_dataset


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
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    root = Path.cwd()
    if args.dataset_command == "fetch":
        path = fetch_dataset(root, args.dataset_id, args.output)
    else:
        path = capture_github_stars(args.user, args.output)
    print(path)
