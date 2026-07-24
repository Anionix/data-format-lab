"""Strict JSON serialization shared by public and persistent writers."""

from __future__ import annotations

import json
import math
from typing import Never, TypedDict, Unpack, cast


class JsonDumpOptions(TypedDict, total=False):
    ensure_ascii: bool
    indent: int | str | None
    separators: tuple[str, str] | None
    sort_keys: bool


def _reject_nonfinite(token: str) -> Never:
    raise json.JSONDecodeError(
        f"non-finite JSON number is not permitted: {token}",
        token,
        0,
    )


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        _reject_nonfinite(token)
    return value


def strict_json_loads(value: str) -> object:
    """Parse RFC 8259 JSON without Python's NaN and Infinity extensions."""
    return cast(
        object,
        json.loads(
            value,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        ),
    )


def strict_json_dumps(value: object, **kwargs: Unpack[JsonDumpOptions]) -> str:
    """Serialize JSON while rejecting values outside the RFC 8259 number grammar."""
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    # RFC 8259 Section 6 excludes NaN and Infinity; reject each value before emission.
    if "allow_nan" in kwargs:
        raise TypeError("allow_nan is fixed to False")
    return json.dumps(value, allow_nan=False, **kwargs)
