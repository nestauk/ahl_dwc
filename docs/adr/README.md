# Architecture decision records

An ADR records **one decision that was expensive to make and would be expensive to reverse**, along
with the constraint that forced it, the options rejected, and — most importantly — what it costs us
now. It is not documentation of how the code works (that is `README.md` and `docs/`), and not a
changelog.

ADRs 0001–0008 were written **retrospectively** in August 2026, reconstructed from git history,
issues and pull requests. Where the record is silent, they say so: an option with no evidence either
way is recorded as "no alternative recorded", not as "rejected". Every claim carries a commit sha or
a `file:line` reference in its Evidence section.

## Format

MADR-lite. One file per decision, `NNNN-kebab-title.md`, with YAML front matter and five sections:

```markdown
---
status: proposed | accepted | superseded
date: YYYY-MM-DD
deciders: name (github-handle)
---

# NNNN. Title

## Context — the constraint that forced a decision, not a narrative

## Decision — what was chosen, active voice

## Alternatives considered — each with why it was not chosen

## Consequences — positive and negative; the negative ones matter most

## Evidence — commit shas, file:line references
```

## Conventions

**Numbering** is a zero-padded four-digit sequence, allocated in order of writing and never reused.
The number is permanent: a superseded ADR keeps its number and its file, and gains a pointer to the
ADR that replaced it.

**Dates** are the real date from git history where the decision is evidenced there. Where it is not —
ADR 0009 — the front matter carries the date the ADR was written and says explicitly that this is
what it is.

**Status**:

| Status       | Meaning                                                                                                                                                  |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `proposed`   | The question is framed; the decision has not been taken.                                                                                                 |
| `accepted`   | Decided and in force. Note that "in force" is not the same as "merged to `main`" — ADR 0007 is accepted but lives on an open PR, and says so at the top. |
| `superseded` | Replaced by a later ADR, which must be named in the file. Nothing is deleted.                                                                            |

**Honesty rule.** The Consequences section must state what the decision costs, not only what it
buys. If a decision means inheriting upstream bugs, or shipping a wheel for one platform only, that
belongs in the ADR, in plain terms.

## Adding one

1. Take the next free number. It must also be the latest date — see the index's ordering rule.
2. Copy the skeleton above into `docs/adr/NNNN-kebab-title.md`.
3. Fill in Evidence as you go — if you cannot cite a commit or a `file:line` for a claim, either
   verify it or write that it is inferred.
4. Add a row to the index below, in the theme the decision belongs to — core architecture, build and
   packaging, Python API surface, quality and verification, release and distribution, or open
   questions. It goes at the bottom of that theme's table, since it is the latest date. If none of
   the six themes fits, add a new one at the end rather than stretching an existing heading.
5. If it replaces an earlier decision, set that ADR's status to `superseded` and cross-link both
   ways.

## Index

The index is ordered on two axes: **theme first, then date within each theme**. The themes run in
the order the work happened, so reading top to bottom also reads chronologically.

The two orderings coincide by design: ADR numbers ascend with decision date
(0001–0005 = 2025-11-20, 0006–0008 = 2026-07-09, 0009 = 2026-08-18), so no file needs renaming to
sit in its group. **A new ADR takes the next free number, and that number must also carry the latest
date** — if you find yourself wanting to record an older decision under a higher number, say so
explicitly in the file rather than breaking the sequence. The first three themes all date from
2025-11-20 and are therefore ordered by number within that day.

Themes are ordered by their **first** decision, so once a theme gains a later ADR its date range can
overlap the themes below it — "Quality and verification" now runs to 2026-08-18 while "Release and
distribution" below it still sits at 2026-07-09. The alternative, reshuffling themes every time one
gains an entry, would make the numbering unstable for no gain.

### Core architecture — how the model gets into Python at all

The two decisions everything else rests on: compile upstream's C++ rather than rewrite it, and
confine the R dependency to one header. Both 2025-11-20.

| #                                        | Title                                                               | Status   | Date       |
| ---------------------------------------- | ------------------------------------------------------------------- | -------- | ---------- |
| [0001](0001-wrap-upstream-bw-cpp.md)     | Wrap upstream `bw`'s C++ rather than reimplement or shell out to R  | accepted | 2025-11-20 |
| [0002](0002-isolate-rcpp-behind-shim.md) | Isolate Rcpp behind `shim.hpp` and keep the model sources unchanged | accepted | 2025-11-20 |

### Build and packaging — how it is compiled and distributed as a package

How the sources become an importable extension, and how the environment and lock around it are
managed. Both 2025-11-20.

| #                                                | Title                                                     | Status   | Date       |
| ------------------------------------------------ | --------------------------------------------------------- | -------- | ---------- |
| [0003](0003-scikit-build-core-pybind11-cmake.md) | scikit-build-core + pybind11 + CMake as the build backend | accepted | 2025-11-20 |
| [0004](0004-uv-packaging-and-lock.md)            | uv as the packaging, environment and lock tool            | accepted | 2025-11-20 |

### Python API surface — what the user touches

The one decision that adds a runtime dependency consumers inherit, rather than shaping the build.
2025-11-20.

| #                                         | Title                                | Status   | Date       |
| ----------------------------------------- | ------------------------------------ | -------- | ---------- |
| [0005](0005-polars-for-tabular-output.md) | Polars for the tabular output helper | accepted | 2025-11-20 |

### Quality and verification — how we know it is right, and on which platforms

The 2026-07-09 hardening pass — a test suite where there was none, and a matrix that compiles the
shim on the toolchains that had already diverged — plus the 2026-08-18 follow-up that made the
static-analysis job satisfiable. 2026-07-09 to 2026-08-18.

| #                                                        | Title                                                                                  | Status              | Date       |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------- | ---------- |
| [0006](0006-test-strategy-unit-regression-tolerances.md) | Test strategy: unit/regression split, `PHYS_RTOL = 1e-4`, Brownian pinned by seed only | accepted            | 2026-07-09 |
| [0007](0007-multiplatform-ci-and-gcc-compat.md)          | Multiplatform CI via tox-uv, and the GCC/libstdc++ compatibility fix                   | accepted (unmerged) | 2026-07-09 |
| [0010](0010-scope-clang-format-to-owned-sources.md)      | Scope clang-format to the sources we own, and make the check blocking                  | accepted (unmerged) | 2026-08-18 |

### Release and distribution — how it reaches consumers

How a tagged version gets to an index consumers can install from, and what that costs. 2026-07-09.

| #                                             | Title                                                                             | Status   | Date       |
| --------------------------------------------- | --------------------------------------------------------------------------------- | -------- | ---------- |
| [0008](0008-codeartifact-publish-via-oidc.md) | Publish to private AWS CodeArtifact via GitHub OIDC, and `unset UV_INDEX` locally | accepted | 2026-07-09 |

### Open questions — not yet decided

Questions framed but not answered. The number is allocated so the question has somewhere to live;
the status stays `proposed` until a decision is taken. 2026-08-18.

| #                                                   | Title                                               | Status   | Date       |
| --------------------------------------------------- | --------------------------------------------------- | -------- | ---------- |
| [0009](0009-evaluate-rust-pyo3-reimplementation.md) | Evaluate a Rust reimplementation with PyO3 bindings | proposed | 2026-08-18 |
