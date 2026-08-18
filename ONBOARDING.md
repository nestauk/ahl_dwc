# Onboarding — `ahl_dwc`

> Hall's Dynamic Weight Change (DWC) model — a Python wrapper around the
> [`bw`](https://github.com/INSP-RH/bw) package's C++ implementation of the
> [Hall et al. adult weight-change model](https://www.niddk.nih.gov/research-funding/at-niddk/labs-branches/LBM/integrative-physiology-section/research-behind-body-weight-planner/Documents/Hall_Lancet_Web_Appendix.pdf).
> Mission prefix `ahl_` = **A Healthy Life** (food, obesity, retail).
>
> This repo was formerly `ahl_hall_model_py`; the primary contact for the
> Python-binding/CI work is Solomon Yu (solomon.yu@nesta.org.uk, GitHub `sqr00t`).

## What this package does

See [`README.md`](README.md) for the user-facing view: purpose, install, quickstart,
the API table and the known sharp edges. Read it first — this document assumes it
and covers only what a contributor needs on top.

In one line: four public names (`adult_weight`, `energy_build`, `results_to_polars`,
`set_seed`), defined in `ahl_dwc/__init__.py`, over a compiled pybind11 extension
`_core` built from `src/`.

## Architecture

```
ahl_dwc/                Python package (the public API)
  __init__.py           adult_weight / energy_build / results_to_polars / set_seed
                        — marshals numpy/list inputs into the C++ wrappers
  _core                 compiled pybind11 extension (built from src/, not committed)

src/                    C++ sources compiled into the _core extension
  bindings.cpp          NEW — pybind11 bindings; registers the `_core` module
                        with adult_weight_wrapper, adult_weight_wrapper_EI,
                        adult_weight_wrapper_EI_fat, EnergyBuilder, set_seed
  shim.hpp              NEW — replaces Rcpp / math.h with std C++ + pybind11:
                        NumericVector / NumericMatrix types, slice support,
                        and the RNG singleton (get_rng / set_seed)
  adult_weight.h        near-identical to bw; edited only to include shim.hpp
                        instead of Rcpp.h / math.h
  adult_weight.cpp      upstream bw code, unchanged
  energy_build.cpp      upstream bw code, plus one added #include "shim.hpp" (line 38)

CMakeLists.txt          builds pybind11 module `_core` from the three .cpp files,
                        installs it into the ahl_dwc/ package
examples/
  reproduce_bw_vignette.py   matplotlib reproduction of the bw vignette
tests/
  unit/test_api.py               input handling + output contracts
  regression/test_adult_weight.py   golden final-weight values (PHYS_RTOL 1e-4)
  regression/test_energy_build.py   interpolation modes + Brownian seeding
```

The three C++ wrapper entry points map to the kwargs supplied in Python:
`adult_weight_wrapper` (base), `adult_weight_wrapper_EI` (when `ei` **or** `fat`
is passed), and `adult_weight_wrapper_EI_fat` (when both are passed). The Python
layer tiles/reshapes `ei_change`/`na_change`, converts sex strings to
`1.0`/`0.0`, transposes matrices to the C++ column layout, and calls the
appropriate wrapper.

### Design note

The porting work isolates all Rcpp/R dependencies into `shim.hpp`, so the
scientific code (`adult_weight.cpp`, `energy_build.cpp`) stays identical to
upstream `bw`. That keeps regressions attributable to the shim / bindings rather
than the model, and it is a rule contributors are expected to hold — see
[`CONTRIBUTING.md`](CONTRIBUTING.md#the-upstream-c-rule).

Caveat on "identical": it means identical _code_. The upstream MIT header
comments were stripped at the initial port and re-added later (`75b1c37`), so the
files have drifted in comments and were not byte-identical at v0. Diff the
function bodies, not the whole file, when re-syncing with upstream.

## Build system & dependencies

- **Build backend:** `scikit-build-core` + `pybind11` (see `[build-system]` in
  `pyproject.toml`). `uv sync` / `uv build` compiles the C++ extension via CMake.
- **Runtime deps:** `numpy>=1.24.4`, `polars>=1.8.2`.
- **Dev group:** `pytest>=7.0`, `ruff`, `pre-commit`, `matplotlib>=3.7.5`,
  `ipykernel`, `jupytext`, `nbstripout`.
- **`requires-python`:** `>=3.8` declared, but CI/`tox` exercises **3.10–3.14**,
  and the declared floor is wrong: `ahl_dwc/__init__.py` uses PEP 604 unions in
  runtime-evaluated signatures with no `from __future__ import annotations`, so
  importing on 3.8/3.9 raises `TypeError`. The real floor is 3.10.
- **Build requirements are not locked.** Neither `scikit-build-core` nor
  `pybind11` appears in `uv.lock` — both resolve fresh at every build, so a
  pybind11 major bump can break the build with no lockfile change. This is the
  largest reproducibility gap in the repo.

## Setup

This is a **uv-based** project (`uv.lock` committed; `[tool.uv] package = true`).

```bash
git clone https://github.com/nestauk/ahl_dwc.git && cd ahl_dwc
direnv allow       # .envrc sources .env and unsets UV_INDEX (keeps local locks on public PyPI)
uv sync            # creates .venv, compiles the _core extension via CMake
prek install       # install the pre-commit hooks
```

Consuming the package rather than developing it? See the install section of
[`README.md`](README.md). Full build detail and its failure modes live in
[`docs/runbooks/local-development.md`](docs/runbooks/local-development.md) — in particular,
`uv sync` will **not** rebuild a stale `_core` after a C++ edit on its own.

## Build & test

```bash
uv run pytest -q                    # run the suite against the current interpreter
uvx --with tox-uv tox run           # full matrix: py3.10–3.14 (as CI does)
```

`testpaths = ["tests"]`. Tests split into:

- **unit** (`tests/unit/`) — API input handling and output-contract checks
  (all time-series keys present, interpolation names accepted, `set_seed`).
- **regression** (`tests/regression/`) — pin known-good numerics. Deterministic
  interpolations and golden final weights use loose relative tolerances
  (`PHYS_RTOL = 1e-4`) to absorb cross-platform libm/FMA differences; the
  Brownian path is pinned only by seed-reproducibility and seed-variance
  (`std::normal_distribution` is not portable across standard libraries).

### Quick smoke test

```python
from ahl_dwc import adult_weight, set_seed
set_seed(623)
out = adult_weight(bw=80, ht=1.8, age=40, sex="female", days=365)
print(out["Body_Weight"][0][-1])   # ~80.0 with no intake change
```

See `examples/reproduce_bw_vignette.py` for a fuller worked example with plots.

## Conventions & tooling

- **Lint/format:** `ruff` (line-length 120, Google docstring convention).
  `ruff check` and `ruff format --check` are **blocking** in CI.
- **C/C++ checks:** `clang-format` is **blocking**, pinned to 22.1.8, and runs over
  `src/shim.hpp` and `src/bindings.cpp` only — style in `.clang-format` at the root.
  The three upstream-derived files are deliberately excluded to keep them
  byte-identical; see [ADR 0010](docs/adr/0010-scope-clang-format-to-owned-sources.md).
  `cppcheck` still covers all of `src/` but stays **advisory** until its version is
  pinned too.
- **pre-commit** (`.pre-commit-config.yaml`): ruff-format/check, standard hygiene
  hooks, `nbstripout`/`jupytext` pairing, prettier, and `no-commit-to-branch`
  for `dev`/`main`. Run `prek run --all-files` before pushing (`prek`, not `pre-commit`).
- **direnv** (`.envrc`): sources `.env`, `unset UV_INDEX` so the private-index
  URL is never baked into `uv.lock` (temporary until the private-index workflow
  is finalised).

## CI (`.github/workflows/`)

| Workflow                   | Trigger                                   | What it does                                                                                                                                                                                                                 |
| -------------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests.yml`                | push to `main`, PRs                       | OS matrix (`ubuntu-latest`, `ubuntu-24.04-arm`, `macos-latest`) x Python 3.10-3.14 driven by `tox-uv`. Linux legs guard the GCC/libstdc++ build.                                                                             |
| `format.yml`               | push to `main`, PRs                       | `ruff` check + format (blocking); `clang-format` over the two owned sources (blocking, pinned 22.1.8); `cppcheck` over all of `src/` (advisory).                                                                             |
| `publish-codeartifact.yml` | GitHub Release published; manual dispatch | `uv build` compiles a platform wheel + sdist, authenticates to AWS via **OIDC** (no long-lived keys), mints a short-lived CodeArtifact token, and `uv publish`es to the private CodeArtifact PyPI. Pre-releases are skipped. |

Two things to know before you touch the publish workflow:

- It builds a **single-platform wheel** (linux/x86_64) on the Linux runner plus an
  sdist; multi-platform wheels would need `cibuildwheel` (tracked as the
  matrix-publish work, issue #9).
- The pre-release guard `if: ${{ !github.event.release.prerelease }}` is **inert on
  `workflow_dispatch`**, because there is no `github.event.release` on that event.
  A manual dispatch will publish whatever tag you name, including a pre-release
  one, and CodeArtifact will not let you overwrite it. See
  [`docs/runbooks/release-and-publish.md`](docs/runbooks/release-and-publish.md).

### Repository state, as of this document

`origin/main` is at `e63a2ce` (the CodeArtifact publish work). Everything after it
— the GCC compatibility fix, the test reorganisation, the tox envs and the
`tests.yml`/`format.yml` split — is unmerged on `fix/gcc-cpp-compat` (PR #10),
with the matrix-publish rewrite open separately as PR #8 on `ci/matrix-build`.
So `main` cannot currently produce a Linux wheel: that is what PR #10 fixes.
`cpp-test-harness` is a local-only branch carrying the same commits; treat it as
stale.

## Documentation map

| Where                                    | What it is for                                                                                                                                                                                        |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`README.md`](README.md)                 | The front door for a _user_ of the package — purpose, install, quickstart, API table, sharp edges, supported platforms                                                                                |
| `ONBOARDING.md` (this file)              | Orientation for someone _joining the work_ — architecture, setup, repo state, where to look first                                                                                                     |
| [`CONTRIBUTING.md`](CONTRIBUTING.md)     | The rules: branch and commit conventions, what CI blocks on, the upstream-C++ rule, when to write an ADR, how to add a regression test and choose a tolerance                                         |
| [`docs/adr/`](docs/adr/)                 | Architecture decision records — the _why_ behind wrapping rather than reimplementing, the `shim.hpp` isolation strategy, Polars, scikit-build-core, CodeArtifact, the GCC fix, the test tolerances    |
| [`docs/runbooks/`](docs/runbooks/)       | Task-shaped guides — local build and rebuild, cutting a release, triaging a failing CI leg                                                                                                            |
| [`docs/ROADMAP.md`](docs/ROADMAP.md)     | Known gaps and planned work: multi-platform wheels, the `requires-python` floor, unlocked build requirements, the private-index arrangement, `child_weight`                                           |
| [`docs/rust-port.md`](docs/rust-port.md) | The standing assessment of a Rust + PyO3 reimplementation — the pains it would and would not fix, the effort, and the triggers that would change the answer. The open question it answers is ADR 0009 |

Anything the docs do not answer is in the issue tracker: #4 (`child_weight`), #7
(GCC/libstdc++), #9 (matrix publish) are the open threads worth reading.

## Where to look first

1. `ahl_dwc/__init__.py` — the public API and how Python inputs map to the C++ wrappers.
2. `src/shim.hpp` — the entirety of the R->C++ porting layer, and the single place a portability bug can bite the whole build.
3. `src/bindings.cpp` — the pybind11 surface.
4. `tests/regression/` — the numerical contract the extension must uphold.
5. `.github/workflows/tests.yml` — the supported platform/Python matrix.
