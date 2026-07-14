from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any

import pyarrow as pa

from format_bench.model import RobustnessExpectation


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    category: str
    expectation: RobustnessExpectation
    parameters: tuple[tuple[str, Any], ...] = ()

    @property
    def options(self) -> dict[str, Any]:
        return dict(self.parameters)


def _case(case_id: str, category: str, **parameters: Any) -> CaseSpec:
    return CaseSpec(
        case_id,
        category,
        RobustnessExpectation.MUST_ROUNDTRIP,
        tuple(sorted(parameters.items())),
    )


def named_cases() -> tuple[CaseSpec, ...]:
    cases = [
        *(_case(f"rows-{rows}", "rows", rows=rows) for rows in (0, 1, 1023, 1024, 1025, 2048, 2049)),
        *(
            _case(f"dictionary-{cardinality}", "dictionary", cardinality=cardinality)
            for cardinality in (1, 2, 255, 256)
        ),
        *(
            _case(f"null-{mode}", "null", mode=mode, rows=17)
            for mode in ("none", "first", "last", "all", "tail")
        ),
        *(
            _case(f"string-{name}", "string", value=value, rows=3)
            for name, value in (
                ("empty", ""),
                ("utf8", "日本語 cafe"),
                ("delimiter", "left|middle,right"),
                ("quote", 'a "quoted" value'),
                ("newline", "line one\nline two"),
                ("long", "x" * 65536),
            )
        ),
        _case("numeric-int64", "numeric", kind="int64", rows=4),
        _case("numeric-float64", "numeric", kind="float64", rows=4),
        CaseSpec("malformed-missing-column", "missing_column", RobustnessExpectation.MUST_REJECT),
        CaseSpec("malformed-extra-column", "extra_column", RobustnessExpectation.MUST_REJECT),
        CaseSpec("malformed-truncated", "truncated_artifact", RobustnessExpectation.MUST_NOT_CRASH),
    ]
    return tuple(cases)


def generated_cases(seed: int, count: int) -> tuple[CaseSpec, ...]:
    if count < 0:
        raise ValueError("generated case count must be non-negative")
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        parameters = {
            "cardinality": rng.randint(1, 256),
            "null_stride": rng.randint(0, 17),
            "rows": rng.randint(0, 2049),
            "string_seed": rng.getrandbits(32),
        }
        encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()
        suffix = hashlib.sha256(encoded).hexdigest()[:10]
        cases.append(
            _case(f"generated-{index:03d}-{suffix}", "generated", **parameters)
        )
    return tuple(cases)


def _rows(table: pa.Table, count: int) -> pa.Table:
    if count == 0:
        return table.slice(0, 0)
    copies = (count + table.num_rows - 1) // table.num_rows
    return pa.concat_tables([table] * copies).slice(0, count)


def _replace(table: pa.Table, name: str, values: list[Any]) -> pa.Table:
    index = table.schema.get_field_index(name)
    field = table.schema.field(index)
    return table.set_column(index, field, pa.array(values, type=field.type))


def materialize_case(base: pa.Table, case: CaseSpec) -> pa.Table:
    if case.expectation is not RobustnessExpectation.MUST_ROUNDTRIP:
        raise ValueError(f"case {case.case_id} has no valid Arrow input")
    options = case.options
    count = options.get("rows", options.get("cardinality", 17))
    table = _rows(base, max(count, options.get("cardinality", 0)))

    if case.category in {"dictionary", "generated"}:
        cardinality = options["cardinality"]
        table = _replace(table, "group", [f"value-{i % cardinality}" for i in range(table.num_rows)])
    if case.category == "null":
        mode = options["mode"]
        values = table["description"].to_pylist()
        nulls = {
            "none": set(),
            "first": {0},
            "last": {len(values) - 1},
            "all": set(range(len(values))),
            "tail": set(range(max(0, len(values) - 2), len(values))),
        }[mode]
        table = _replace(table, "description", [None if i in nulls else value for i, value in enumerate(values)])
    if case.category == "string":
        table = _replace(table, "description", [options["value"]] * table.num_rows)
    if case.category == "numeric":
        if options["kind"] == "int64":
            table = _replace(table, "repo_stars", [-(2**63), -1, 0, 2**63 - 1])
        else:
            table = _replace(table, "classification_score", [-1.7976931348623157e308, -0.0, 0.0, 1.7976931348623157e308])
    if case.category == "generated":
        seed = options["string_seed"]
        values = [f"generated-{seed:08x}-{i}" for i in range(table.num_rows)]
        if options["null_stride"]:
            stride = options["null_stride"]
            values = [None if i % stride == 0 else value for i, value in enumerate(values)]
        table = _replace(table, "description", values)
    return table
