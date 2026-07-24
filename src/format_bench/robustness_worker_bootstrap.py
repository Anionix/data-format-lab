from __future__ import annotations

from format_bench.worker_limits import apply_worker_resource_limits


def main() -> None:
    effective_limits = apply_worker_resource_limits()
    # Import the heavyweight adapter and robustness graph only after hard caps apply.
    from format_bench.robustness.worker import main as worker_main

    worker_main(effective_limits)


if __name__ == "__main__":
    main()
