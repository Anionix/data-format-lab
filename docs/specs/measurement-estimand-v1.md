# Measurement estimand v1

## Scope

Each fair or equivalence run preregisters `measurement.estimand` before its
first benchmark job. The contract defines what the latency fields estimate; it
does not make a causal or population-wide performance claim.

The structure adapts the population, condition, variable, and population-level
summary attributes from the FDA/ICH
[E9(R1) estimand framework](https://www.fda.gov/media/148473/download).
E9(R1) also distinguishes an estimand (the target) from an estimator (the
method) and estimate (the result). Data Format Lab applies that distinction to
software measurements, not clinical trials.

## Populations and condition

- The data population is every row in one immutable dataset snapshot, pinned
  by dataset ID, row count, and source SHA-256. It does not represent the
  source service's wider or future population.
- The timing population is every scheduled fresh child process under the
  recorded system, dataset, workload, and measurement configuration.
- The comparison condition is the declared format, operation, and settings.
  Generalization beyond the recorded system, dataset, and workload is `none`.

## Latency targets

| Target | Variable per process | Estimator | Evidence |
| --- | --- | --- | --- |
| `fresh_p50_ms` | First invocation elapsed time, excluding validation | Linear-interpolated p50 across processes | `fresh_samples_ms` |
| `warm_p50_ms` | Median post-warmup invocation elapsed time, excluding validation | Median of process medians | `warm_process_p50_ms` |
| `warm_p95_ms` | p95 post-warmup invocation elapsed time, excluding validation | Median of process linear-interpolated p95s | `warm_process_p95_ms` |

Published estimates are rounded to three decimal places.

`warm` pools nested iterations from all processes. It remains useful
descriptive evidence, but it is not an independent inferential sample. This
process-level boundary follows NIST TN 1830's warning that caching and other
stateful behavior can violate an i.i.d. interpretation of repeated timings:
[The Ghost in the Machine](https://www.nist.gov/publications/ghost-machine-dont-let-it-haunt-your-software-performance-measurements).

## Execution and failures

The first invocation runs in a new worker process after worker setup; it is not
process-startup latency. The OS cache is not purged. Warmups and timed
iterations retain process state. Correctness validation runs outside the timer.

A timeout, nonzero exit, malformed worker result, count mismatch, or validation
failure fails the job. No latency is imputed and no failed process is silently
removed. `UNSUPPORTED`, `FAILED`, `INCONCLUSIVE`, and `NOT_APPLICABLE` retain
their lane-specific meanings and are never converted into measured latency.
