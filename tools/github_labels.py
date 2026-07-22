"""Pure deterministic planning for GitHub repository labels."""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote


@dataclass(frozen=True)
class LabelSpec:
    name: str
    color: str
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "color", self.color.lower())


@dataclass(frozen=True)
class LabelMutation:
    method: Literal["POST", "PATCH"]
    path: str
    key: str
    payload: dict[str, object]


def _index(specs: tuple[LabelSpec, ...], context: str) -> dict[str, LabelSpec]:
    result: dict[str, LabelSpec] = {}
    for spec in specs:
        if (key := spec.name.casefold()) in result:
            raise ValueError(f"duplicate {context} label: {spec.name}")
        result[key] = spec
    return result


def plan_labels(
    repository: str, desired: tuple[LabelSpec, ...], current: tuple[LabelSpec, ...]
) -> tuple[LabelMutation, ...]:
    wanted, live = _index(desired, "desired"), _index(current, "live")
    result: list[LabelMutation] = []
    for key in sorted(wanted):
        spec, actual = wanted[key], live.get(key)
        if actual is None:
            result.append(LabelMutation("POST", f"repos/{repository}/labels", spec.name,
                                        {"name": spec.name, "color": spec.color, "description": spec.description}))
        elif actual != spec:
            result.append(LabelMutation("PATCH", f"repos/{repository}/labels/{quote(actual.name, safe='')}", spec.name,
                                        {"new_name": spec.name, "color": spec.color, "description": spec.description}))
    return tuple(result)
