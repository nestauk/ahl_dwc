# Contributing to `ahl_dwc`

This is a small repo with an unusual shape: a thin Python layer over C++ that is deliberately kept identical to an upstream R package. Most of the rules below exist to protect that split.

## Development setup

Do not follow instructions here — follow [`docs/runbooks/local-development.md`](docs/runbooks/local-development.md), which is the single source of truth for getting a working environment and rebuilding the extension after a C++ edit. In outline it is `uv sync`, then `uv run pytest -q`; the runbook covers the failure modes (stale `_core`, missing toolchain, `UV_INDEX` polluting `uv.lock`) that will otherwise cost you an afternoon.

Two things to do once, before your first commit:

```bash
direnv allow          # activates .envrc, which unsets UV_INDEX
prek install          # installs the pre-commit hooks (prek, not pre-commit)
```

## Branches

Branch from `main`. Naming follows the type prefixes already in the history:

| Prefix   | Used for                            | Examples in this repo                                                          |
| -------- | ----------------------------------- | ------------------------------------------------------------------------------ |
| `feat/`  | new capability                      | `feat/porting-adult-weight`, `feat/results-to-df`, `feat/codeartifact-publish` |
| `fix/`   | bug fix                             | `fix/gcc-cpp-compat`                                                           |
| `ci/`    | workflow and CI configuration       | `ci/matrix-build`                                                              |
| `clean/` | tidy-ups, consistency work, renames | `clean/improvements`                                                           |

Add `docs/`, `test/` or `build/` prefixes as needed — match the Conventional Commits type you would use for the work.

**`main` and `dev` are protected locally** by the `no-commit-to-branch` pre-commit hook (`.pre-commit-config.yaml`), so a direct commit to either is blocked before it happens. (There is no `dev` branch in this repo; the hook guards it anyway.) Everything lands through a pull request.

## Commits

Conventional Commits, imperative subject, no trailing full stop. Types in use: `feat`, `fix`, `ci`, `build`, `test`, `chore`, `docs`, `refactor`, `perf`. Add a scope when the change is confined to one area:

```
fix(shim): remove duplicate NumericVector ctors for GCC compat
ci: replace ci.yml with multiplatform tests.yml + format.yml
build: add [tool.tox] py3.10-3.14 test envs (tox-uv)
```

Keep commits atomic — one unit of meaning each. Lockfile bumps, workflow edits and source changes belong in separate commits. Do not add model-authorship or "generated with" trailers.

Run the hooks before pushing:

```bash
prek run                      # staged files
prek run --files <paths>      # a specific set
prek run --all-files          # everything, before a PR
```

`prek` is the Rust drop-in for `pre-commit` and reads the same `.pre-commit-config.yaml`; plain `pre-commit` is not installed on the standard Nesta setup. Note that the `pre-commit-update` hook bumps hook revisions on its own, so `.pre-commit-config.yaml` will occasionally change under you — commit that separately as `chore:`.

## What CI will block on

Three workflows run (see [`docs/runbooks/ci-triage.md`](docs/runbooks/ci-triage.md) for diagnosing a red check).

| Check                                                                                                                          | Blocking?                     | Notes                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------ | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests.yml` — `uvx --with tox-uv tox run` on `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-latest`, each across Python 3.10–3.14 | **Yes**                       | `fail-fast: false`, so you see all three legs. The Linux legs guard the GCC/libstdc++ build path — never "fix" a red Linux leg by removing it                                                                                                                        |
| `format.yml` job `python` — `ruff check .` and `ruff format --check .`, pinned to 0.14.10                                      | **Yes**                       | Same version as `.pre-commit-config.yaml`, so `prek run` locally is equivalent. If you bump one, bump the other                                                                                                                                                      |
| `format.yml` job `cpp` — `clang-format` pinned to 22.1.8, over `src/shim.hpp` and `src/bindings.cpp` only                      | **Yes**                       | Style is `.clang-format` at the repo root. The three upstream files are deliberately excluded — see [ADR 0010](docs/adr/0010-scope-clang-format-to-owned-sources.md). Run `prek run clang-format --all-files` before pushing; the hook is pinned to the same version |
| `format.yml` job `cpp` — `cppcheck` over all of `src/`                                                                         | No (step `continue-on-error`) | Advisory only because the apt version is not pinned, so a runner-image bump can add diagnostics that are not a regression in our code. It passes clean today — **open the log** if you touched C++                                                                   |
| `publish-codeartifact.yml`                                                                                                     | n/a                           | Only fires on a published GitHub Release                                                                                                                                                                                                                             |

Ruff config lives in `pyproject.toml`: line length 120, `select = ["ANN", "B", "C", "E", "F", "I", "N", "W"]`, Google docstring convention. Tests are exempt from `ANN`, `D100` and `D103`.

## The upstream C++ rule

`src/adult_weight.cpp` and `src/energy_build.cpp` hold **the upstream [`INSP-RH/bw`](https://github.com/INSP-RH/bw) code, unchanged**, and must stay that way. Two caveats on "unchanged", both verified: `src/energy_build.cpp:38` adds `#include "shim.hpp"`, and `src/adult_weight.h:32` replaces upstream's `math.h`/`Rcpp.h` includes with the same header. The claim is about the code, not about bytes — see [`docs/adr/0002-isolate-rcpp-behind-shim.md`](docs/adr/0002-isolate-rcpp-behind-shim.md) and [`docs/runbooks/upstream-sync.md`](docs/runbooks/upstream-sync.md). This is the whole point of the port: it makes every numerical regression attributable to `shim.hpp` or `bindings.cpp` rather than to the model, and it lets us re-sync with upstream cheaply.

If you believe one of those files must change:

1. **Try to fix it in `shim.hpp` first.** Nearly every portability problem so far has been a shim problem, not a model problem — the GCC constructor ambiguity in `bf87e07` is the worked example.
2. If it genuinely cannot be fixed in the shim, **open an issue first** describing the divergence and why it is unavoidable. Do not fold it into an unrelated PR.
3. If it is a bug in the model rather than in the port, raise it upstream with `INSP-RH/bw` and record the local patch as a deliberate, isolated divergence with an ADR.
4. **Write an ADR** (below) recording exactly which lines diverge, so the next person re-syncing with upstream knows what not to clobber.

Reformatting those files counts as changing them. This is why the `clang-format` check names `src/shim.hpp` and `src/bindings.cpp` explicitly instead of globbing `src/` — see [ADR 0010](docs/adr/0010-scope-clang-format-to-owned-sources.md). **If you add a first-party C++ file, add it to both `.github/workflows/format.yml` and `.pre-commit-config.yaml`**; nothing detects the omission, and an unlisted file is silently unchecked.

Changing C++ has a second cost: keep C++ source changes in their own PR, separate from CI configuration changes, so the compiled behaviour and the build config are reviewed independently. That precedent is set by PR #8 (CI) and PR #10 (the C++ fix) being deliberately split.

## When to write an ADR

Add a record under [`docs/adr/`](docs/adr/) when a change would leave a future reader asking "why on earth is it like this?". Concretely:

- Choosing or replacing a dependency that consumers inherit (Polars, NumPy, a new runtime dep).
- Changing the build chain (scikit-build-core, pybind11, CMake options, pinning a C++ standard).
- Changing the publishing or distribution story (cibuildwheel, a second index, wheel platforms).
- Any divergence from upstream `bw`, per the rule above.
- Changing a numerical contract — tolerances, golden values, the integration scheme, the `days` off-by-one-step behaviour.
- Deliberately _not_ doing something obvious, and why (for example, why `child_weight` is not wrapped).

Routine bug fixes, test additions and dependency bumps do not need one. A one-page record beats a perfect one that never gets written.

## Adding a regression test

Tests live in `tests/`, split by intent:

- `tests/unit/` — input handling and output contracts. No physiology: does the right wrapper get called, are all ten time-series keys present, does `results_to_polars` return the long shape.
- `tests/regression/` — pins the numerics. `test_adult_weight.py` holds golden final weights per wrapper variant; `test_energy_build.py` covers the interpolation modes.

To add one:

1. Put it in the right directory. If it would still pass after a real model change, it is a unit test.
2. Parameterise over the axis you actually care about rather than copying the test body.
3. Capture the expected value from a **clean build** on your machine, and say so in a comment — including which wrapper variant and which inputs produced it. The existing golden values are documented as "captured from the reference build", with no committed script; do not make that worse. Ideally, record the generating snippet in the docstring.
4. State in the docstring what a failure would mean. The point of a golden value is that someone who breaks it knows whether they have found a bug or a floating-point difference.

### Choosing a tolerance

Match the tolerance to why the number is what it is. The suite already demonstrates all four tiers below; ADR [`0006`](docs/adr/0006-test-strategy-unit-regression-tolerances.md) records why each was chosen.

| Kind of assertion                                               | Tolerance                | Why                                                                                                                                                                                                  |
| --------------------------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Analytically exact — no intake change leaves weight at baseline | `atol=1e-6` against 80.0 | The answer is exact; anything else is a bug                                                                                                                                                          |
| Analytically derivable — `energy_build` `Linear`                | `rtol=1e-9`              | Closed-form interpolation, only rounding should differ                                                                                                                                               |
| Physiological output of the ODE integration                     | `PHYS_RTOL = 1e-4`       | Loose enough to absorb cross-platform libm and FMA differences, tight enough that a real regression (order 0.1 kg and up) fails. Genuine regressions shift results by whole kilograms                |
| Anything consuming the RNG (Brownian)                           | **Do not pin values**    | `std::normal_distribution` is implementation-defined and not portable across standard libraries. Pin the properties instead: same seed gives identical output, different seeds give different output |

If you find yourself loosening a tolerance to make a test pass, stop — that is the test doing its job. Work out which of the four rows your assertion belongs in, and if it genuinely is a cross-platform difference, say so in a comment with the platforms you compared.

## Pull requests

- One concern per PR. C++ separate from CI, as above.
- Say what changed, why, and what you verified — including which platforms you ran on, since macOS and Linux have already diverged once at compile time.
- Link the issue the PR closes.
- All three green: `tests.yml` on every leg, `format.yml`'s `python` job, and — if you touched C++ — the `cpp` job's log read by eye, since it will not fail for you.
- If you touched `ahl_dwc/__init__.py`'s public signatures, update the API table in `README.md` in the same PR.
- If you made a decision worth an ADR, the ADR goes in the same PR as the change.
