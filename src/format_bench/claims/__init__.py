from __future__ import annotations

from typing import TYPE_CHECKING

from .fastlanes import run_fastlanes_claim

if TYPE_CHECKING:
    from .tsfile import run_tsfile_claim
    from .vortex import run_vortex_stress

__all__ = ["run_fastlanes_claim", "run_tsfile_claim", "run_vortex_stress"]


def __getattr__(name: str):
    if name == "run_tsfile_claim":
        from .tsfile import run_tsfile_claim

        return run_tsfile_claim
    if name == "run_vortex_stress":
        from .vortex import run_vortex_stress

        return run_vortex_stress
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
