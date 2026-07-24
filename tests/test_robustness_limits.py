import resource

import pytest

import format_bench.worker_limits as worker_limits
from format_bench.worker_limits import (
    EffectiveWorkerResourceLimits,
    WorkerResourceLimits,
    apply_worker_resource_limits,
)


def test_worker_limits_lower_hard_caps_and_preserve_tighter_inheritance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_limits.sys, "platform", "linux")
    monkeypatch.setattr(
        worker_limits, "_real_user_process_limit_supported", lambda: True
    )
    requested = WorkerResourceLimits(
        address_space_bytes=800,
        file_size_bytes=400,
        open_files=200,
        real_user_processes=20,
    )
    inherited = {
        resource.RLIMIT_AS: (resource.RLIM_INFINITY, resource.RLIM_INFINITY),
        resource.RLIMIT_FSIZE: (resource.RLIM_INFINITY, 300),
        resource.RLIMIT_NOFILE: (50, 100),
        resource.RLIMIT_NPROC: (resource.RLIM_INFINITY, 10),
    }
    applied: dict[int, tuple[int, int]] = {}
    monkeypatch.setattr(
        resource,
        "getrlimit",
        lambda resource_id: inherited[resource_id],
    )
    monkeypatch.setattr(
        resource,
        "setrlimit",
        lambda resource_id, limits: applied.__setitem__(resource_id, limits),
    )

    effective = apply_worker_resource_limits(requested)

    assert effective == EffectiveWorkerResourceLimits(800, 300, 50, 10)
    assert applied == {
        resource.RLIMIT_AS: (800, 800),
        resource.RLIMIT_FSIZE: (300, 300),
        resource.RLIMIT_NOFILE: (50, 50),
        resource.RLIMIT_NPROC: (10, 10),
    }


def test_worker_limits_record_darwin_address_space_as_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_limits.sys, "platform", "darwin")
    monkeypatch.setattr(
        worker_limits, "_real_user_process_limit_supported", lambda: True
    )
    requested = WorkerResourceLimits(800, 400, 200, 20)
    inherited = {
        resource.RLIMIT_FSIZE: (resource.RLIM_INFINITY, 300),
        resource.RLIMIT_NOFILE: (50, 100),
        resource.RLIMIT_NPROC: (resource.RLIM_INFINITY, 10),
    }
    applied: dict[int, tuple[int, int]] = {}
    monkeypatch.setattr(
        resource,
        "getrlimit",
        lambda resource_id: inherited[resource_id],
    )
    monkeypatch.setattr(
        resource,
        "setrlimit",
        lambda resource_id, limits: applied.__setitem__(resource_id, limits),
    )

    effective = apply_worker_resource_limits(requested)

    assert effective == EffectiveWorkerResourceLimits(
        None, 300, 50, 10, ("address_space_bytes",)
    )
    assert resource.RLIMIT_AS not in applied
    assert applied == {
        resource.RLIMIT_FSIZE: (300, 300),
        resource.RLIMIT_NOFILE: (50, 50),
        resource.RLIMIT_NPROC: (10, 10),
    }


def test_worker_limits_do_not_claim_privileged_nproc_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_limits.sys, "platform", "linux")
    monkeypatch.setattr(
        worker_limits, "_real_user_process_limit_supported", lambda: False
    )
    requested = WorkerResourceLimits(800, 400, 200, 20)
    inherited = {
        resource.RLIMIT_AS: (resource.RLIM_INFINITY, resource.RLIM_INFINITY),
        resource.RLIMIT_FSIZE: (resource.RLIM_INFINITY, 300),
        resource.RLIMIT_NOFILE: (50, 100),
    }
    applied: dict[int, tuple[int, int]] = {}
    monkeypatch.setattr(
        resource,
        "getrlimit",
        lambda resource_id: inherited[resource_id],
    )
    monkeypatch.setattr(
        resource,
        "setrlimit",
        lambda resource_id, limits: applied.__setitem__(resource_id, limits),
    )

    effective = apply_worker_resource_limits(requested)

    assert effective == EffectiveWorkerResourceLimits(
        800, 300, 50, None, ("real_user_processes",)
    )
    assert resource.RLIMIT_NPROC not in applied


def test_privileged_linux_context_does_not_support_nproc_enforcement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_limits.sys, "platform", "linux")
    monkeypatch.setattr(worker_limits.os, "getuid", lambda: 501)
    monkeypatch.setattr(
        worker_limits,
        "_linux_effective_capabilities",
        lambda: 1 << worker_limits._CAP_SYS_RESOURCE,
    )

    assert worker_limits._real_user_process_limit_supported() is False

    monkeypatch.setattr(worker_limits.os, "getuid", lambda: 0)
    monkeypatch.setattr(
        worker_limits, "_linux_effective_capabilities", lambda: 0
    )
    assert worker_limits._real_user_process_limit_supported() is False
