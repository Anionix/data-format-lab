"""Strict JSON serialization shared by public and persistent writers."""

from __future__ import annotations

import json
from typing import TypedDict, Unpack


class JsonDumpOptions(TypedDict, total=False):
    ensure_ascii: bool
    indent: int | str | None
    separators: tuple[str, str] | None
    sort_keys: bool


def strict_json_dumps(value: object, **kwargs: Unpack[JsonDumpOptions]) -> str:
    """Serialize JSON while rejecting values outside the RFC 8259 number grammar."""
    # LLM contract: DISCOVERED -> ENCODED -> ROUNDTRIP_VERIFIED -> BENCHMARKED -> REPORTED.
    # RFC 8259 Section 6 excludes NaN and Infinity; reject each value before emission.
    if "allow_nan" in kwargs:
        raise TypeError("allow_nan is fixed to False")
    return json.dumps(value, allow_nan=False, **kwargs)
