from __future__ import annotations

import os
import resource
import sys
from dataclasses import dataclass
from pathlib import Path

_CAP_SYS_ADMIN = 21
_CAP_SYS_RESOURCE = 24


@dataclass(frozen=True)
class WorkerResourceLimits:
    address_space_bytes: int
    file_size_bytes: int
    open_files: int
    real_user_processes: int

    def evidence(self) -> dict[str, int]:
        return {
            "address_space_bytes": self.address_space_bytes,
            "file_size_bytes": self.file_size_bytes,
            "open_files": self.open_files,
            "real_user_processes": self.real_user_processes,
        }


@dataclass(frozen=True)
class EffectiveWorkerResourceLimits:
    address_space_bytes: int | None
    file_size_bytes: int
    open_files: int
    real_user_processes: int | None
    unsupported_resources: tuple[str, ...] = ()

    def evidence(self) -> dict[str, int | None]:
        return {
            "address_space_bytes": self.address_space_bytes,
            "file_size_bytes": self.file_size_bytes,
            "open_files": self.open_files,
            "real_user_processes": self.real_user_processes,
        }


DEFAULT_WORKER_RESOURCE_LIMITS = WorkerResourceLimits(
    address_space_bytes=8 * 1024**3,
    file_size_bytes=1024**3,
    open_files=256,
    real_user_processes=512,
)


def _effective_limit(resource_id: int, requested: int) -> int:
    inherited_soft, inherited_hard = resource.getrlimit(resource_id)
    effective = requested
    for inherited in (inherited_soft, inherited_hard):
        if inherited != resource.RLIM_INFINITY:
            effective = min(effective, inherited)
    return effective


def _linux_effective_capabilities() -> int | None:
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in status.splitlines():
        name, separator, value = line.partition(":")
        if name == "CapEff" and separator:
            try:
                return int(value.strip(), 16)
            except ValueError:
                return None
    return None


def _real_user_process_limit_supported() -> bool:
    # Linux getrlimit contract:
    # https://man7.org/linux/man-pages/man2/getrlimit.2.html
    if os.getuid() == 0:
        return False
    if sys.platform != "linux":
        return True
    capabilities = _linux_effective_capabilities()
    exempt = (1 << _CAP_SYS_ADMIN) | (1 << _CAP_SYS_RESOURCE)
    return capabilities is not None and capabilities & exempt == 0


def effective_worker_resource_limits(
    limits: WorkerResourceLimits = DEFAULT_WORKER_RESOURCE_LIMITS,
) -> EffectiveWorkerResourceLimits:
    """Derive caps without relaxing tighter inherited soft or hard limits."""

    # Python resource contract: https://docs.python.org/3.12/library/resource.html
    address_space_supported = sys.platform != "darwin"
    process_limit_supported = _real_user_process_limit_supported()
    unsupported_resources = []
    if not address_space_supported:
        unsupported_resources.append("address_space_bytes")
    if not process_limit_supported:
        unsupported_resources.append("real_user_processes")
    return EffectiveWorkerResourceLimits(
        address_space_bytes=(
            _effective_limit(resource.RLIMIT_AS, limits.address_space_bytes)
            if address_space_supported
            else None
        ),
        file_size_bytes=_effective_limit(
            resource.RLIMIT_FSIZE, limits.file_size_bytes
        ),
        open_files=_effective_limit(resource.RLIMIT_NOFILE, limits.open_files),
        real_user_processes=(
            _effective_limit(resource.RLIMIT_NPROC, limits.real_user_processes)
            if process_limit_supported
            else None
        ),
        unsupported_resources=tuple(unsupported_resources),
    )


def apply_worker_resource_limits(
    limits: WorkerResourceLimits = DEFAULT_WORKER_RESOURCE_LIMITS,
) -> EffectiveWorkerResourceLimits:
    """Install non-raiseable caps and return their effective values."""

    effective = effective_worker_resource_limits(limits)
    resource_limits = [
        (resource.RLIMIT_FSIZE, effective.file_size_bytes),
        (resource.RLIMIT_NOFILE, effective.open_files),
    ]
    if effective.address_space_bytes is not None:
        resource_limits.insert(
            0, (resource.RLIMIT_AS, effective.address_space_bytes)
        )
    if effective.real_user_processes is not None:
        resource_limits.append(
            (resource.RLIMIT_NPROC, effective.real_user_processes)
        )
    for resource_id, value in resource_limits:
        resource.setrlimit(resource_id, (value, value))
    # LLM contract: limit setup failure becomes HARNESS_FAILED, incomplete,
    # non-ranking evidence; successful setup never advances lifecycle state.
    return effective
