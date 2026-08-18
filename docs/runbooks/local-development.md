# Runbook: local development

Goal: from a fresh clone to `30 passed`, and back to green after editing C++.

`ahl_dwc` is a compiled package. Every `uv sync` runs CMake and a C++ compiler; there is
no pure-Python fallback. Most local problems are build problems, not Python problems.

## 0. Prerequisites

| Tool | Why | Check |
|---|---|---|
| C++ compiler | `src/*.cpp` is compiled into the `_core` extension | `c++ --version` |
| CMake >= 3.15 | `CMakeLists.txt:1` | `cmake --version` |
| uv | dependency and build driver (`[tool.uv] package = true`) | `uv --version` |
| direnv (optional but recommended) | applies `.envrc`, which does `unset UV_INDEX` | `direnv --version` |

Compiler install, per platform:

```bash
# macOS
xcode-select --install

# Debian / Ubuntu
sudo apt-get update && sudo apt-get install -y build-essential cmake
```

Notes:

- No C++ standard is pinned. `CMakeLists.txt` sets no `CMAKE_CXX_STANDARD` and pybind11's
  exported targets propagate no `cxx_std_*` feature, so you get the compiler's default.
  This has already caused one GCC-only breakage — see `src/shim.hpp:45-56`.
- CMake and Ninja do not strictly need to be on `PATH`: `scikit-build-core` will resolve
  wheel-provided ones if the system copies are unsuitable. Installing them anyway makes
  failures easier to read.
- Windows is not tested by CI and no wheel is built for it. Treat it as unsupported.

## 1. Clone and allow direnv

```bash
git clone https://github.com/nestauk/ahl_dwc.git
cd ahl_dwc
direnv allow    # only if direnv is installed
```

`.envrc` sources `.env` if present and then runs `unset UV_INDEX`. That unset is what keeps
the private CodeArtifact index URL out of the committed `uv.lock`. If you do not use direnv,
prefix locking commands with `env -u UV_INDEX` (see the troubleshooting table).

## 2. Sync — this is the build step

```bash
uv sync
```

What it does: creates `.venv`, installs runtime deps (numpy, polars) and the `dev` group,
then builds `ahl_dwc` itself through `scikit_build_core.build`. That invokes CMake, which
runs `find_package(pybind11 REQUIRED CONFIG)` and compiles `src/bindings.cpp`,
`src/adult_weight.cpp` and `src/energy_build.cpp` into `_core`, installed into `ahl_dwc/`.

Expected: verbose CMake configure and compile lines (`build.verbose = true`,
`logging.level = "INFO"` in `pyproject.toml:5-7`), ending with the environment resolved.

Confirm the extension imports:

```bash
uv run python -c "import ahl_dwc; print(ahl_dwc.adult_weight, ahl_dwc._core)"
```

Note: build-time requirements (`scikit-build-core`, `pybind11`) are **not** in `uv.lock` —
they are resolved fresh on every build. A pybind11 major release can therefore break your
build with no change to the repository.

## 3. Run the tests

```bash
uv run pytest -q
```

Expected: `30 passed` in well under a second (`[tool.pytest.ini_options] testpaths = ["tests"]`).

Layout:

| Path | Covers |
|---|---|
| `tests/unit/test_api.py` | Python-side marshalling, kwargs dispatch, `results_to_polars` shape |
| `tests/regression/test_adult_weight.py` | Golden final weights for the three wrapper variants, `PHYS_RTOL = 1e-4` |
| `tests/regression/test_energy_build.py` | Interpolation modes; Brownian pinned by seed behaviour only, never by value |

## 4. Run one test

```bash
uv run pytest tests/regression/test_adult_weight.py -q
uv run pytest "tests/regression/test_adult_weight.py::test_adult_weight_golden_final_weight[ei_variant]" -q
uv run pytest -q -k brownian
```

## 5. Rebuild after editing C++ — the stale-extension trap

Editing `src/shim.hpp`, `src/adult_weight.cpp`, `src/energy_build.cpp` or `src/bindings.cpp`
and rerunning `pytest` **can silently use the previously compiled `_core`**. Symptoms: your
change has no effect, or `AttributeError` on a symbol you just added to `bindings.cpp`.
Compiled artefacts are gitignored, so nothing warns you.

Force a rebuild:

```bash
uv sync --reinstall-package ahl-dwc
uv run pytest -q
```

If that is not enough, remove the artefacts and sync again:

```bash
rm -rf build
find ahl_dwc -name '*.so' -delete
uv sync
```

The authoritative cross-check is a tox leg, which always builds into a fresh environment:

```bash
uvx --with tox-uv tox run -e py312 -r
```

(The `--reinstall-package` incantation is the practical fix; the repository documents no
rebuild target and there is no Makefile.)

## 6. Run the tox matrix as CI does

```bash
uv python install 3.10 3.11 3.12 3.13 3.14
uvx --with tox-uv tox run            # all of py310..py314
uvx --with tox-uv tox run -e py312   # one leg
```

`[tool.tox]` in `pyproject.toml:37-45` uses the `uv-venv-lock-runner`, installs the `dev`
group and runs `pytest -q`. CI runs exactly `uvx --with tox-uv tox run` on
`ubuntu-latest`, `ubuntu-24.04-arm` and `macos-latest`.

Note `requires-python = ">=3.8"` in `pyproject.toml:14` is wrong in practice: `ahl_dwc/__init__.py`
uses PEP 604 `X | Y` annotations at runtime with no `from __future__ import annotations`, so
import fails on 3.8/3.9. Nothing tests below 3.10, so do not develop against 3.8 or 3.9.

## 7. Run the example

```bash
uv run python examples/reproduce_bw_vignette.py
```

Expected: printed baseline and scenario weights, and four PNG files written **into the
current working directory** — the script takes no output path. Run it from a scratch
directory if you do not want the files in the repo root:

```bash
mkdir -p /tmp/dwc-plots && cd /tmp/dwc-plots && \
  uv --project /path/to/ahl_dwc run python /path/to/ahl_dwc/examples/reproduce_bw_vignette.py
```

It needs matplotlib, which is in the `dev` group only — `uv sync` installs it, a plain
consumer install does not.

## 8. Lint before committing

```bash
uvx ruff@0.14.10 check .
uvx ruff@0.14.10 format --check .
prek run --files <paths>     # the repo's pre-commit hooks; `pre-commit` itself is not installed
```

Version `0.14.10` matches `.pre-commit-config.yaml` and `.github/workflows/format.yml`. Note
`no-commit-to-branch` blocks commits to `main` and `dev`; work on a branch.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Could not find a package configuration file provided by "pybind11"` | Build isolation was disabled, so the `requires = ["scikit-build-core", "pybind11"]` build deps were never installed | Build with isolation (plain `uv sync`). If you must disable it: `uv pip install scikit-build-core pybind11 cmake ninja` into the env first |
| `CMake 3.15 or higher is required` | System CMake too old and no wheel fallback picked up | Install a current CMake (`brew install cmake` / `apt-get install cmake`) |
| Compile fails with no compiler found | No toolchain | macOS: `xcode-select --install`. Linux: `apt-get install build-essential` |
| C++ edit has no effect; `AttributeError` on a new binding | Stale compiled `_core` in the editable install | `uv sync --reinstall-package ahl-dwc`, or step 5's full clean |
| Compiles on macOS, fails on Linux with an "ambiguous" overload | GCC/libstdc++ resolves overloads more strictly than Clang/libc++ | See `docs/runbooks/ci-triage.md`; precedent is commit `bf87e07` and the comment at `src/shim.hpp:45-56` |
| `git diff uv.lock` shows `codeartifact...amazonaws.com` URLs | `UV_INDEX` was set in the shell when you ran `uv lock` / `uv add` | `direnv allow`, then `env -u UV_INDEX uv lock`; verify with `grep -c 'pypi.org/simple' uv.lock` and `grep -c codeartifact uv.lock` (expect 0) |
| `TypeError: unsupported operand type(s) for \|` on import | Running on Python 3.8/3.9, which `requires-python` wrongly permits | Use Python >= 3.10 |
| Brownian `energy_build` output differs between runs | The RNG defaults to `std::random_device`; only `set_seed` makes it reproducible, and only within a process | Call `ahl_dwc.set_seed(n)` first; do not expect the same values on another platform |
| A regression test fails only on your machine | Likely libm/FMA drift, not a model change | Follow the decision procedure in `docs/runbooks/ci-triage.md` |
