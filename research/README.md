# Negative and Incomplete Evidence

An unavailable build is not a zero-performance result. Each record in `research/formats/` identifies the primary source, pinned commit, attempted entrypoint, observed failure, and the condition required for a new attempt.

Supporting probe manifests live under `research/probes/`. They pin dependency versions and acquisition sources without turning an unsupported build into a performance result.

These records are reported in the claims lane but never ranked. A future successful run creates a new observation; it does not rewrite the historical failure.

The v0.1 attempts were run on macOS ARM in the same pinned Nix toolchain used by the measured formats. Large upstream source checkouts and build directories are not vendored.
