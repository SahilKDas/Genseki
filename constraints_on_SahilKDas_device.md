# Constraints on SahilKDas's Device

This file is the binding local resource contract for developing, training,
testing, packaging, and running Genseki on SahilKDas's laptop. Its purpose is
to protect the machine's storage, memory, responsiveness, and any active match
or online-engine sessions. These limits apply even when a larger workload would
improve Genseki. Only SahilKDas may explicitly relax them.

## Hardware snapshot

Snapshot taken on 2026-10-03. Free disk space, free memory, and driver versions
are point-in-time values.

| Component | Verified specification |
| --- | --- |
| Laptop | HP Pavilion Laptop 15-eg2xxx |
| CPU | 12th Gen Intel Core i7-1255U; 10 physical cores, 12 logical processors |
| Memory installed | 16,831,832,064 bytes installed |
| Memory visible to Windows | 16,437,336 KiB visible, about 15.68 GiB |
| Free physical memory at snapshot | 3,412,900 KiB, about 3.25 GiB |
| Discrete GPU | NVIDIA GeForce MX550; 2,147,483,648 bytes reported VRAM; driver 32.0.15.9282 |
| Integrated GPU | Intel Iris Xe Graphics; shared-memory adapter; driver 32.0.101.5542 |
| Operating system | Microsoft Windows 11 Home, 64-bit; version 10.0.26200, build 26200 |
| System drive at snapshot | 510,694,256,640 bytes total; 17,211,322,368 bytes free |

The integrated GPU memory reported by Windows is shared system memory, so it
must not be treated as an additional dedicated training budget.

## Hard limits

| Resource or activity | Limit |
| --- | --- |
| Genseki engine search | At most 12 CPU search threads per engine process |
| All temporary project data combined | At most 10,000,000,000 bytes (10 GB) at any instant |
| Temporary neural training data and artifacts | At most 6,000,000,000 bytes (6 GB) at any instant, included inside the 10 GB total cap |
| Concurrent CPU-heavy training or gauntlet jobs | At most 1 unless SahilKDas explicitly authorizes more |
| Concurrent online bridge or match-controller processes | At most 2 |
| Concurrent Genseki GUI processes | At most 2 |
| Raspberry Pi emulation or heavy Linux/ARM environments | Do not create or run them on this laptop without new explicit permission |

The 6 GB training allowance is a subset of the 10 GB total temporary-data
allowance, not an additional allowance. For example, 6 GB of training data
leaves at most 4 GB for every other temporary Genseki file combined. When
classification is unclear, count the data toward the cap.

## What counts as temporary data

The 10 GB total includes all disposable data created or downloaded for a
Genseki task, regardless of which directory or drive contains it:

- compiler, linker, LTO, CMake, and build-tree scratch data;
- downloaded archives, extracted dependency copies, and temporary toolchains;
- training inputs, sampled positions, tensors, candidate networks, checkpoints,
  caches, and training logs;
- generated match records, suites, benchmark output, screenshots, crash dumps,
  and validation evidence that is not intentionally retained;
- package staging directories, extracted ZIP copies, and duplicate release
  candidates.

Checked-in source files and deliberately retained, hash-pinned dependencies are
not temporary merely because they support a build. A new task must still count
any disposable copies it creates from them.

Before a storage-heavy task begins, estimate peak usage and measure current
temporary usage. Stop before either cap would be exceeded; do not rely on
cleanup after an overrun. Delete disposable staging and temporary data when the
task is complete while preserving tracked source, reproducibility records, and
test evidence the repository intentionally keeps.

## CPU, memory, and process rules

- Genseki's production search contract is capped at twelve CPU threads, one
  for each logical processor reported by Windows. Do not
  silently raise protocol thread count, helper count, or parallel-search lane
  count.
- GPU execution is controlled independently by the CUDA runtime. CUDA cores do
  not map one-to-one to engine search threads, so the 12-thread CPU limit must
  not be interpreted as a GPU worker or CUDA-core limit.
- Do not run multiple CPU-heavy gauntlets or training jobs concurrently unless
  SahilKDas explicitly authorizes that specific run.
- Keep long background matches and benchmarks bounded. When foreground use or
  an online bridge/match controller is active, use Windows Idle priority for
  background gauntlets where supported.
- Neural training may use available physical memory aggressively, but must
  leave at least 0.5 GiB free. If available memory falls below that floor,
  stop or shrink the job.
- Very deep fixed-depth searches can take hours on this device. Depth ladders
  and matches must have declared time, game-count, and storage bounds rather
  than running indefinitely.
- Never exceed two online bridge/match-controller processes or two GUI
  processes. The limits are per category, not a shared total: two controllers
  plus two GUIs is permitted, while three controllers or three GUIs is not.

## Protect active play

Do not interrupt a running online bridge, match controller, or live engine game
merely to build, test, install, or replace Genseki. For a bridge/controller
upgrade:

1. Leave the active process untouched.
2. Start at most one replacement, staying within the two-controller limit.
3. Confirm that the replacement starts correctly and reaches its service.
4. Only then close the old process.

Avoid builds, installs, cleanup commands, or process-wide termination that can
overwrite an executable used by an active process, kill its process tree, or
remove its configuration. Never expose, copy into a release, or commit private
tokens or credentials stored in ignored local configuration files.

## GUI visibility

When SahilKDas asks to watch engine games or GUI tests, launch the GUI visibly
and do not hide it in the background. Headless correctness tests are still
allowed when no visible GUI was requested. A visible test does not override the
two-GUI limit.

## Local build and release storage

- Treat `dist/current` as a rolling release-candidate directory, not an archive.
- Keep only the newest required Windows candidate packages there.
- Remove obsolete local candidate folders, extracted package duplicates, and
  superseded build scratch after they are no longer needed.
- Do not delete tracked validation evidence, reproducibility manifests, active
  configuration, or a binary currently used by an active process.

## Preflight and completion checklist

Before a resource-heavy task:

1. Confirm projected peak storage stays within both the 10 GB total cap and,
   when applicable, the nested 6 GB training cap.
2. Confirm projected RAM use leaves at least 0.5 GiB free memory.
3. Confirm no conflicting training or gauntlet is already running.
4. Count active bridge/controller and GUI processes.
5. Protect live play and keep the laptop usable for foreground work.
6. State bounds for game count, time, and generated storage.

After the task:

1. Verify correctness before retaining a candidate.
2. Remove disposable temporary data and obsolete local build duplicates.
3. Re-measure temporary storage when the task was storage-heavy.
4. Leave only current required candidate packages under `dist/current`.

This document is intentionally tracked by Git and must not be added to
`.gitignore`.
