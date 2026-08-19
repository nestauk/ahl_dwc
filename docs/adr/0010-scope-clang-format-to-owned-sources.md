---
status: accepted
date: 2026-08-18
deciders: Solomon Yu (sqr00t)
---

# 0010. Scope clang-format to the sources we own, and make the check blocking

## Context

The `cpp` job in `.github/workflows/format.yml` had failed on **every run since it was added**. It
ran `clang-format --dry-run --Werror --style=Google` over `src/*.cpp src/*.hpp src/*.h`, which
includes `adult_weight.h`, `adult_weight.cpp` and `energy_build.cpp` — the files
[ADR 0002](0002-isolate-rcpp-behind-shim.md) requires to stay byte-identical to upstream
`INSP-RH/bw`. Those files are not Google-formatted and, under that policy, never can be. The check
was unsatisfiable by construction.

`continue-on-error: true` at job level meant this never blocked a merge, so the failure was tolerated
rather than fixed. Two things followed:

1. Every pull request carried a red X that everyone had learned to ignore — including
   [ADR 0007](0007-multiplatform-ci-and-gcc-compat.md), which recorded the situation as a known
   consequence rather than a defect.
2. **`cppcheck` never executed.** The clang-format step failed first and the job stopped there. When
   it was finally run, `cppcheck` reported two real `uninitMemberVarNoCtor` warnings in `shim.hpp`
   that had been invisible for the entire life of the job.

The second point is what forced the decision. A static-analysis job that cannot pass is not merely
noisy — it silently withholds the findings it exists to produce.

[`ROADMAP.md`](../ROADMAP.md) task 3.2 identified the blocker correctly: the problem is not doing the
formatting pass, it is deciding how the upstream sources are exempted from it.

## Decision

Scope the formatting check to the two files this project owns, and make it blocking.

- **Check `src/shim.hpp` and `src/bindings.cpp` only**, named explicitly in the workflow rather than
  matched by a glob. The three upstream-derived files are not formatted and not checked.
- **Check in a `.clang-format`** at the repository root: `BasedOnStyle: Google`, with
  `BreakBeforeBraces: Allman` and `ColumnLimit: 120`. These two departures describe the code as it is
  actually written, here and upstream, instead of rewriting it. `ColumnLimit: 120` matches
  `line-length = 120` in `pyproject.toml`.
- **Pin the formatter**: `uvx clang-format@22.1.8`, mirroring `uvx ruff@0.14.10`. A matching
  `pre-commit` hook is added at the same pin, restricted to the same two files.
- **Drop job-level `continue-on-error`**, so a formatting regression in first-party C++ fails the
  build.
- **Pin `cppcheck` and make it blocking too**, still running over all of `src/`. It comes from PyPI
  via `uvx --from cppcheck==1.5.1` (Cppcheck 2.17.1), not from apt: the apt install wedged for over
  an hour on three separate CI runs and offers no version guarantee either. `--check-level=exhaustive`
  is set because otherwise cppcheck emits an informational `normalCheckLevelMaxBranches` notice on
  `energy_build.cpp` that `--error-exitcode` counts as a failure; analysing every branch is the
  honest fix, suppressing the notice is not.

  Analysing the upstream sources is not in tension with keeping them byte-identical — cppcheck reads,
  it does not rewrite. That is why its scope is all of `src/` while clang-format's is two files.

## Alternatives considered

**A repo-wide formatting pass over all of `src/`.** Rejected: it reformats the three upstream files
and forfeits the byte-identical property, which is the mechanism
[`runbooks/upstream-sync.md`](../runbooks/upstream-sync.md) relies on to make re-syncing with `bw`
cheap. This is the obvious fix and the one to guard against.

**Pin the exact upstream commit of each vendored file and diff against it in CI, then format
everything.** Floated as item (c3) in [`rust-port.md`](../rust-port.md). Rejected _for now_ on cost,
not on merit: it needs a per-file provenance record and a CI job to enforce it, which is more
machinery than the problem currently justifies. It remains the better answer if the number of
vendored files grows, and it is the alternative to revisit if the explicit file list starts drifting
from reality.

**Leave the job non-blocking and simply narrow the file list.** Rejected: it fixes the red X without
fixing the underlying property that nobody is ever required to read the output. The `cppcheck`
warnings above are the evidence that advisory checks do not get read.

**Install `cppcheck` from apt, pinned with `apt-get install cppcheck=<version>`.** Rejected on
reliability rather than on pinning: the apt path wedged for over an hour on three separate runs
before this ADR was finalised, which is what forced the move off it. Ubuntu also carries only the
version in its archive for a given release, so the pin would be dictated by the runner image rather
than chosen.

**Use raw Google style on the two owned files.** Rejected on diff size. Measured before choosing:

| File               | Violations under raw Google | Under this `.clang-format` |
| ------------------ | --------------------------- | -------------------------- |
| `src/shim.hpp`     | 299                         | 38                         |
| `src/bindings.cpp` | 64                          | 15                         |

Raw Google would have meant a ~300-line rewrite of the load-bearing shim for no behavioural gain.

## Consequences

**Positive.**

- The `cpp` job can pass, and now genuinely gates first-party C++ formatting.
- `cppcheck` runs, and its findings are visible. Two latent warnings were fixed as a direct result.
- Pinning removes the failure mode that made the job untrustworthy in the first place: an unpinned
  apt `clang-format` changes output between major versions, so a runner-image bump alone could turn
  the check red with no change to our code.
- The exemption is explicit and readable in the workflow, rather than implied by a glob.

**Negative.**

- **The file list is manual and will drift.** A new first-party `.cpp` or `.hpp` will not be checked
  until someone adds it to both `format.yml` and `.pre-commit-config.yaml`. There is no mechanism
  that notices the omission. This is the direct cost of choosing the cheap exemption over (c3).
- **Two pins to keep in step**, `format.yml` and `.pre-commit-config.yaml`, with nothing enforcing
  that they match — the same duplication that already exists for ruff.
- **Two more pinned versions to maintain** — `clang-format@22.1.8` and `cppcheck==1.5.1` — each of
  which will eventually need a deliberate bump, and each of which can surface a batch of new
  diagnostics when bumped. That is the price of not being at the mercy of a runner image, but it is
  a real maintenance obligation rather than a free win.
- **`uvx` is now on the critical path for the C/C++ checks.** Both tools are fetched from PyPI at job
  time, so a PyPI outage fails the `cpp` job. This replaces a dependency on apt with a dependency on
  PyPI; the argument for it is that the apt path demonstrably wedged three times in one day, not
  that PyPI is infallible.
- The upstream files remain **unformatted**, though not unanalysed: `cppcheck` covers them. A
  formatting defect there is invisible to CI by design, and a `cppcheck` finding in one of them
  cannot be fixed locally without breaking byte-identity — it has to go upstream.

**Supersedes part of ADR 0007.** That ADR records "C/C++ static checks are added but non-blocking" as
an accepted consequence. That is no longer true of either check: clang-format and cppcheck both
block, and both are version-pinned. ADR 0007 keeps its number and its status; a pointer to this ADR
has been added to the relevant consequence.

## Evidence

- The unsatisfiable check, before this change: `.github/workflows/format.yml` `cpp` job,
  `clang-format --dry-run --Werror --style=Google src/*.cpp src/*.hpp src/*.h` under
  `continue-on-error: true`
- The failure it produced, on PR #10: run `29997811499`, job `89175565748` — clang-format violations
  reported in `src/adult_weight.h` among others, then `##[error]Process completed with exit code 1`,
  with the `cppcheck` step never reached
- The two warnings this unblocked: `shim.hpp` `ColProxy::col` in both `NumericMatrix` and
  `StringMatrix`, `uninitMemberVarNoCtor`; fixed in `85a398c` on PR #10
- The change itself: PR #21, `df30f48` (`.clang-format` plus formatting of the two owned files) and
  `c504b9d` (workflow and pre-commit hook)
- Byte-identity policy this preserves: [ADR 0002](0002-isolate-rcpp-behind-shim.md),
  [`runbooks/upstream-sync.md`](../runbooks/upstream-sync.md)
- The blocker this resolves: [`ROADMAP.md`](../ROADMAP.md) tasks 3.2 and 3.3
