from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from format_bench.model import ObservedOutcome


SOURCE_COMMIT = "f0edc1020a538f1f8098640fce8347c9ac247a0d"
PACKAGE = "pyfastlanes==0.1.3.post9"
DELIMITER = "|"
STRING_BOUNDARIES = (1023, 1024, 1025, 2048, 2049)
MIXED_ROWS = 1024


def _run_case(directory: Path, name: str, rows: int, timeout_seconds: float) -> dict:
    directory = directory.resolve()
    case_dir = directory / name
    case_dir.mkdir(parents=True, exist_ok=True)
    command = (
        sys.executable,
        "-m",
        "format_bench.claims.fastlanes_worker",
        "--case",
        name.split("-", 1)[0],
        "--rows",
        str(rows),
        "--output",
        str(case_dir),
    )
    environment = os.environ.copy()
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "format_bench").is_dir():
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(source_root), environment.get("PYTHONPATH")) if part
        )
    try:
        completed = subprocess.run(
            command,
            cwd=directory,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or "", error.stderr or ""
        process = {"returncode": None, "timed_out": True, "signal": None}
    else:
        stdout, stderr = completed.stdout, completed.stderr
        process = {
            "returncode": completed.returncode,
            "timed_out": False,
            "signal": -completed.returncode if completed.returncode < 0 else None,
        }
    (case_dir / "stdout.txt").write_text(stdout, encoding="utf-8", errors="replace")
    (case_dir / "stderr.txt").write_text(stderr, encoding="utf-8", errors="replace")
    result = {"case": name, "rows": rows, "process": process}
    if process["timed_out"]:
        result["outcome"] = ObservedOutcome.TIMED_OUT
    elif process["signal"] is not None:
        try:
            result["signal_name"] = signal.Signals(process["signal"]).name
        except ValueError:
            result["signal_name"] = None
        result["outcome"] = ObservedOutcome.CRASHED
    elif completed.returncode != 0:
        result["outcome"] = ObservedOutcome.HARNESS_FAILED
    else:
        try:
            result.update(json.loads(stdout.strip().splitlines()[-1]))
            if "outcome" not in result:
                result["outcome"] = ObservedOutcome.HARNESS_FAILED
        except (IndexError, json.JSONDecodeError) as error:
            result["outcome"] = ObservedOutcome.HARNESS_FAILED
            result["error"] = f"invalid worker output: {error}"
    return result


def _fatal_cases(
    numeric: dict,
    strings: dict[str, dict],
    malformed: dict,
    mixed: dict | None = None,
) -> list[dict]:
    fatal = []
    if numeric.get("outcome") != ObservedOutcome.ROUNDTRIP_EQUAL:
        fatal.append(numeric)
    fatal.extend(
        item
        for item in (*strings.values(), malformed, *((mixed,) if mixed is not None else ()))
        if item.get("status") == "FAILED"
        or item.get("outcome")
        in {
            ObservedOutcome.CRASHED,
            ObservedOutcome.TIMED_OUT,
            ObservedOutcome.HARNESS_FAILED,
        }
    )
    return fatal


def run_fastlanes_claim(
    directory: Path,
    *,
    numeric_rows: int = 1_000_000,
    string_boundaries: tuple[int, ...] = STRING_BOUNDARIES,
    timeout_seconds: float = 900.0,
) -> dict:
    if importlib.util.find_spec("pyfastlanes") is None:
        raise ModuleNotFoundError(f"optional dependency is unavailable: {PACKAGE}")
    import pyfastlanes

    directory.mkdir(parents=True, exist_ok=True)
    numeric = _run_case(directory, "numeric-8-columns", numeric_rows, timeout_seconds)
    strings = {
        str(rows): _run_case(directory, f"string-{rows}", rows, timeout_seconds)
        for rows in string_boundaries
    }
    mixed = _run_case(directory, "mixed-13-columns", MIXED_ROWS, timeout_seconds)
    malformed = _run_case(directory, "comma-malformed", max(string_boundaries), timeout_seconds)
    boundary_summary = ",".join(
        f"{rows}={item.get('outcome', item.get('status', 'UNKNOWN'))}"
        for rows, item in strings.items()
    )
    fatal = _fatal_cases(numeric, strings, malformed, mixed)
    root = directory.parent.parent
    return {
        "status": "FAILED" if fatal else "MEASURED",
        "reason": "; ".join(item["case"] for item in fatal) if fatal else None,
        "source_commit": SOURCE_COMMIT,
        "package": PACKAGE,
        "package_version": version("pyfastlanes"),
        "runtime_version": pyfastlanes.get_version(),
        "delimiter": DELIMITER,
        "target_tier": "EXPERIMENTAL",
        "project_seeded": True,
        "numeric": numeric,
        "string_boundaries": strings,
        "mixed": mixed,
        "comma_malformed": malformed,
        "summary": (
            f"numeric={numeric.get('outcome', numeric.get('status', 'UNKNOWN'))}; "
            f"strings={boundary_summary}; "
            f"mixed={mixed.get('outcome', mixed.get('status', 'UNKNOWN'))}; "
            f"comma={malformed.get('outcome', malformed.get('status', 'UNKNOWN'))}"
        ),
        "artifacts_root": str(directory.relative_to(root)),
    }
