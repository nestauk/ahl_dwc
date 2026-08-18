---
status: accepted
date: 2026-07-09
deciders: Solomon Yu (sqr00t)
---

# 0007. Multiplatform CI via tox-uv, and the GCC/libstdc++ compatibility fix

> **Not yet on `main`.** The C++ fix and the workflows live on `fix/gcc-cpp-compat` (PR #10, open);
> `origin/main` is at `e63a2ce`. The decision is accepted and implemented, but a Linux wheel is still
> not producible from `main`.

## Context

Until 2026-07-09 there was no CI on this repo at all, and the only platform anyone had built on was
macOS. That mattered more than usual here, because the package compiles C++ at install time
(ADR 0003) with **no C++ standard pinned** and a hand-written shim (ADR 0002) whose type surface sits
exactly where compilers diverge.

The divergence surfaced concretely. `src/shim.hpp` declared `NumericVector` with
`using std::vector<double>::vector;` _and_ redeclared `NumericVector()`, `NumericVector(size_t)` and
`NumericVector(size_t, double)`. Call sites pass an `int`:

```
src/shim.hpp:186:43: error: call of overloaded 'NumericVector(int&, double)' is ambiguous
```

Both the inherited `vector(size_type, const value_type&)` and the redeclared `(size_t, double)`
require the same `int → size_t` conversion, so neither is better. GCC rejects this per the standard;
Clang resolves it. macOS built; every Linux build failed (issue #7).

## Decision

Two decisions, deliberately kept in separate pull requests.

**1. Fix the ambiguity by deleting our redeclarations** (`bf87e07`). Keep only
`using std::vector<double>::vector;` and the `const std::vector<double>&` converting constructor, and
record the reasoning in the source itself (`src/shim.hpp:49-55`):

> We deliberately do NOT redeclare the (n) and (n, v) constructors here: doing so made calls like
> `NumericVector(int, 0.0)` ambiguous under GCC/libstdc++ … which broke Linux builds while compiling
> fine under Clang/libc++. The inherited ctors are behaviourally identical (`vector(n)`
> value-initialises to 0.0).

**2. Build a matrix that would have caught it.** The OS dimension is the GitHub matrix; the Python
dimension is delegated to tox (ADR 0004):

| Dimension        | Where it lives                                       | Values                                              |
| ---------------- | ---------------------------------------------------- | --------------------------------------------------- |
| Operating system | `.github/workflows/tests.yml:21`, `fail-fast: false` | `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-latest` |
| Python version   | `[tool.tox] env_list` in `pyproject.toml:39`         | 3.10, 3.11, 3.12, 3.13, 3.14                        |

Three jobs cover fifteen environments. The workflow header states the purpose: "Python 3.10–3.14 are
driven by `[tool.tox]` (tox-uv); the OS matrix is the GitHub dimension. The Linux legs guard the
GCC/libstdc++ build."

The first CI (`a931e2f`, a single `ci.yml`) was replaced by `7a9d3e5` with two workflows, which
carried two further decisions:

- **Lint is split from test**, with separate concurrency groups (`tests-${{ github.ref }}`,
  `format-${{ github.ref }}`, both `cancel-in-progress`).
- **C/C++ static checks are added but non-blocking.** `format.yml`'s `cpp` job runs
  `clang-format --dry-run --Werror --style=Google` and
  `cppcheck --enable=warning,portability --error-exitcode=1` under `continue-on-error: true`
  (`.github/workflows/format.yml:30`), justified in the header as surfacing issues "without failing
  the build on the ported code's pre-existing formatting … until a dedicated clang-format pass
  lands". Python ruff stays blocking, pinned to `0.14.10` to match `.pre-commit-config.yaml`.

  > **Superseded for clang-format** by [ADR 0010](0010-scope-clang-format-to-owned-sources.md).
  > That pass has now landed: clang-format is pinned, scoped to `shim.hpp` and `bindings.cpp`, and
  > blocking. `cppcheck` remains advisory. This ADR keeps its number and status; only this
  > consequence is out of date.

**3. Sequence the two changes separately.** Issue #7 records that the C++ change was "Deferred out of
the matrix-CI work so that C++ source changes are reviewed separately from CI config" — hence PR #8
(CI/publish matrix) and PR #10 (C++ fix) as two open PRs, with #8's Linux legs non-blocking until #10
lands.

## Alternatives considered

| Alternative                                                       | Why not chosen                                                                                                                                                                                    |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-fpermissive`                                                    | Rejected in issue #7: this is "a hard error, not a warning" — the flag does not apply.                                                                                                            |
| Cast the call-site argument to `size_t`                           | Rejected in issue #7: "the ambiguity is by-value vs const-ref, both exact matches" — the cast does not disambiguate.                                                                              |
| Keep the redeclared constructors and drop the Linux leg           | Would ship a package that cannot be built on the platform most consumers and all CI runners use. The Linux legs exist precisely to guard this.                                                    |
| Pin `CMAKE_CXX_STANDARD` and hope the standard version settles it | Does not help: the ambiguity is standard-conformant behaviour, not a dialect difference. Pinning the standard is still worth doing for other reasons (ADR 0003) and remains undone.               |
| Put Python versions in the GitHub matrix                          | Would make 15 jobs and, more importantly, would leave no way to reproduce a specific version locally. Delegating to tox means `uvx --with tox-uv tox run -e py312` reproduces one CI leg exactly. |
| Make the C/C++ checks blocking now                                | Impossible without violating ADR 0002 — the upstream sources are not Google-formatted and must not be reformatted.                                                                                |

## Consequences

Positive:

- The exact failure that motivated this cannot recur silently: two Linux legs (x86_64 and arm64)
  compile the shim on GCC/libstdc++ on every push and PR.
- `fail-fast: false` means one broken leg does not hide the state of the others.
- The Python dimension is reproducible locally, byte-for-byte with CI, from `pyproject.toml`.
- The fix is behaviour-preserving by construction: `vector(n)` value-initialises to `0.0`, and
  nothing in the codebase uses brace-init, so the inherited constructors are drop-in.
- The reasoning is in the source file, where the next person to "tidy up" those constructors will
  read it.

Negative:

- **Neither PR has merged.** `main` still cannot produce a Linux wheel, and `main`'s publish workflow
  (ADR 0008) builds exactly that — one linux/x86_64 wheel — on a commit where, per issue #7, the
  compile could not have succeeded.
- **The `cpp` job fails on every run without blocking anything.** `continue-on-error` is set at job
  level, so the _workflow_ passes while the job itself reports `fail` — a permanent red X that
  everyone learns to ignore. Worse, the failure is in the first step: `clang-format` exits non-zero
  over the upstream sources, so `cppcheck` never runs at all. Two genuine `uninitMemberVarNoCtor`
  warnings in `shim.hpp` sat unreported for the whole life of the job.

  > **Resolved** by [ADR 0010](0010-scope-clang-format-to-owned-sources.md) and PR #21. The
  > cppcheck warnings themselves were fixed in `85a398c` on this PR.

- **No Windows leg.** Windows is untested and unsupported in fact, though nothing says so in
  `pyproject.toml`.
- **Nothing below Python 3.10 is exercised**, while `requires-python = ">=3.8"`
  (`pyproject.toml:14`) invites 3.8/3.9 installs that cannot import the package.
- The `cpp` step globs `src/*.cpp src/*.hpp src/*.h`; all three patterns match today
  (`shim.hpp` is the only `.hpp`, `adult_weight.h` the only `.h`), but if a category ever empties the
  glob goes unexpanded and clang-format errors on a literal path (inferred).
- The ruff pin is duplicated by hand in `format.yml:22` and `.pre-commit-config.yaml:27`, while a
  `pre-commit-update` hook auto-bumps the latter — so the two drift apart on their own.
- No toolchain step installs a compiler or CMake; the workflow relies on the runner image plus
  scikit-build-core's wheel-provided `cmake`/`ninja`. A runner image change can break the build with
  no repo change.

## Evidence

- `bf87e07` (2026-07-09 12:53) "fix: remove duplicate NumericVector ctors for GCC compat; add tests";
  diff on `src/shim.hpp` removes the three constructors and adds the six-line rationale comment.
- `src/shim.hpp:46-56` — the surviving `using` declaration and the comment.
- Issue #7 (open) — the error text, the rejected workarounds, the reproduction on `g++-16` locally
  and GCC 13 on `ubuntu-latest`, and the sequencing rationale. PR #10 (open).
- `a931e2f` (2026-07-09) adds `ci.yml`; `7a9d3e5` (2026-07-23) deletes it and adds `tests.yml`
  (37 lines) and `format.yml` (38).
- `.github/workflows/tests.yml:3-6` (header), `:11-13` (concurrency), `:18-21` (matrix),
  `:31-37` (uv python install, tox run, `UV_PYTHON_PREFERENCE: only-managed`).
- `.github/workflows/format.yml:3-6` (header), `:17-26` (blocking ruff), `:29-38` (non-blocking cpp).
- `pyproject.toml:37-45` (`[tool.tox]`), added in `dd4e80f`.
- `0ac4dff` on `ci/matrix-build` (PR #8) — the matching three-leg publish matrix.
