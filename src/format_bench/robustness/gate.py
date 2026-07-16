from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from format_bench.model import RobustnessVerdict, TargetTier


JsonObject = dict[str, object]


def _cases(payload: object) -> list[JsonObject]:
    if not isinstance(payload, dict) or payload.get("profile") != "robustness":
        raise ValueError("results must contain profile: robustness")
    results = payload.get("results")
    if not isinstance(results, dict):
        raise ValueError("results must contain a results object")
    evidence = results.get("robustness_v1")
    if not isinstance(evidence, dict):
        raise ValueError("results must contain robustness_v1 evidence")
    cases = evidence.get("cases")
    if not isinstance(cases, list) or not all(isinstance(case, dict) for case in cases):
        raise ValueError("robustness_v1 cases must be a list of objects")
    typed_cases = [cast(JsonObject, case) for case in cases]
    valid_tiers = {tier.value for tier in TargetTier}
    valid_verdicts = {verdict.value for verdict in RobustnessVerdict}
    for case in typed_cases:
        if case.get("tier") not in valid_tiers:
            raise ValueError("robustness case has an invalid target tier")
        if case.get("verdict") not in valid_verdicts:
            raise ValueError("robustness case has an invalid verdict")
    return typed_cases


def core_failures(payload: object) -> list[JsonObject]:
    return [
        case
        for case in _cases(payload)
        if case.get("tier") == TargetTier.CORE.value
        and case.get("verdict") == RobustnessVerdict.FAIL.value
    ]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fail only for bounded robustness CORE target failures."
    )
    parser.add_argument("results", type=Path)
    args = parser.parse_args(argv)
    payload: object = json.loads(args.results.read_text(encoding="utf-8"))
    cases = _cases(payload)
    failures = core_failures(payload)
    if failures:
        print(
            "core robustness failures: "
            + json.dumps(failures, sort_keys=True, ensure_ascii=True),
            file=sys.stderr,
        )
        raise SystemExit(1)
    core_count = sum(case.get("tier") == TargetTier.CORE.value for case in cases)
    experimental_count = sum(
        case.get("tier") == TargetTier.EXPERIMENTAL.value for case in cases
    )
    print(
        "bounded robustness gate passed: "
        f"{core_count} core cases, {experimental_count} experimental observations"
    )


if __name__ == "__main__":
    main()
