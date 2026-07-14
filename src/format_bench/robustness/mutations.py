from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MutationRecipe:
    mutation_id: str
    operation: str
    parameters: tuple[tuple[str, Any], ...] = ()

    @property
    def options(self) -> dict[str, Any]:
        return dict(self.parameters)


def mutation_recipes(size: int, seed: int, count: int) -> tuple[MutationRecipe, ...]:
    if size < 0 or count < 0:
        raise ValueError("mutation size and count must be non-negative")
    rng = random.Random(seed)
    operations = ("empty", "truncate", "flip_header", "flip_middle", "flip_footer", "zero_range", "append")
    recipes = []
    for index in range(count):
        operation = operations[index % len(operations)]
        parameters: dict[str, Any] = {}
        if operation == "truncate":
            parameters["offset"] = rng.randint(0, size)
        elif operation.startswith("flip_"):
            region = operation.removeprefix("flip_")
            if region == "header":
                start, stop = 0, min(size, 64)
            elif region == "middle":
                start, stop = max(0, size // 2 - 32), min(size, size // 2 + 32)
            else:
                start, stop = max(0, size - 64), size
            parameters["offset"] = rng.randrange(start, stop) if stop > start else 0
            parameters["mask"] = 1 << rng.randrange(8)
        elif operation == "zero_range":
            start = rng.randrange(size) if size else 0
            parameters.update(offset=start, length=rng.randint(1, min(64, max(1, size - start))))
        elif operation == "append":
            parameters["hex"] = rng.randbytes(8).hex()
        encoded = json.dumps([operation, parameters], sort_keys=True, separators=(",", ":")).encode()
        suffix = hashlib.sha256(encoded).hexdigest()[:10]
        recipes.append(
            MutationRecipe(
                f"mutation-{index:03d}-{operation}-{suffix}",
                operation,
                tuple(sorted(parameters.items())),
            )
        )
    return tuple(recipes)


def apply_mutation(data: bytes, recipe: MutationRecipe) -> bytes:
    options = recipe.options
    if recipe.operation == "empty":
        return b""
    if recipe.operation == "truncate":
        return data[: options["offset"]]
    if recipe.operation == "append":
        return data + bytes.fromhex(options["hex"])
    if not recipe.operation.startswith("flip_") and recipe.operation != "zero_range":
        raise ValueError(f"unknown mutation operation: {recipe.operation}")
    mutated = bytearray(data)
    offset = options["offset"]
    if recipe.operation.startswith("flip_"):
        if offset < len(mutated):
            mutated[offset] ^= options["mask"]
    elif recipe.operation == "zero_range":
        stop = min(len(mutated), offset + options["length"])
        mutated[offset:stop] = b"\0" * (stop - offset)
    return bytes(mutated)
