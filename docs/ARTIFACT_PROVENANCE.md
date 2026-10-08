# Artifact Verification

`python -m genseki.artifacts manifest.json` runs a read-only doctor. It reports
missing files, mismatched hashes, unsafe paths, incomplete build provenance and
unverified effective settings. It never downloads, restores or substitutes a
model. A nonzero exit means the manifest cannot support a reproducible run.

Schema version 1 contains `artifacts`, `provenance`, and `effective_settings`.
Artifact roles include executable, model, calibration, referee and openings;
each used artifact has a repository-relative POSIX path and SHA256. Optional
unused artifacts are explicitly null. Source hashes use the same notation.

Imported executables use provenance kind `imported-binary`. A
`verified-source-build` requires revision, compiler, pinned dependencies,
build command, source file hashes and `build_exit_code: 0`. This is evidence
validation, not independent proof that an arbitrary binary was built from those
sources. Retain the actual build log and verify its identity separately.
The doctor checks source hashes against the current checkout by default. Match
loading checks frozen binary/dependency hashes, not evolving checkout sources;
source provenance must already have been corroborated when the build was frozen.

Effective settings contain requested and verified mappings, plus evidence of
the verification (for example, retained engine option responses). A requested
setting alone does not establish the engine's effective setting. The checker
rejects disagreement. Do not include host paths, usernames or raw tracebacks.

The match runner accepts `--a-manifest` and `--b-manifest`, validates artifact
hashes before every game and compares effective engine option readback to the
frozen settings. Runs without both manifests remain explicitly unverified
imports. The deterministic opening-seed plan is hash-pinned, and the actual
opening moves are retained in each game. Seed plans are not sealed qualification.

The team scheduling lock is `.tmp/team-genseki/heavy.lock`; application exclusion
is `reports/work/heavy-job.lock`. Both use nonblocking exclusive ownership of
byte zero on Windows, or flock on POSIX. Acquire scheduling ownership first,
retain both for the full heavy job, and never interpret file existence as a
live lock. Failed acquisition must not bypass resource guards.
