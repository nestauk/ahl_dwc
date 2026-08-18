---
status: accepted
date: 2025-11-20
deciders: Harry Wilde (HarrisonWilde)
---

# 0003. scikit-build-core + pybind11 + CMake as the build backend

## Context

The package is a compiled extension (ADR 0001): three `.cpp` files must be compiled and linked into
a Python module that ships inside the `ahl_dwc` package directory. The build has to work from a
plain `uv sync` for developers, from an sdist for consumers without a wheel, and inside a CI runner
with no bespoke setup.

The upstream code is written against Rcpp, whose type surface the shim (ADR 0002) mirrors onto
C++/Python casts. A binding library with a comparable type-casting model was therefore the natural
fit.

## Decision

We build with **scikit-build-core** as the PEP 517 backend, **pybind11** for the bindings and
**CMake** as the build system.

```toml
[build-system]
requires = ["scikit-build-core", "pybind11"]
build-backend = "scikit_build_core.build"

[tool.scikit-build]
build.verbose = true
logging.level = "INFO"
```

The entire build definition is 13 lines of CMake:

```cmake
cmake_minimum_required(VERSION 3.15)
project(ahl_dwc)
find_package(pybind11 REQUIRED CONFIG)
pybind11_add_module(_core src/bindings.cpp src/adult_weight.cpp src/energy_build.cpp)
target_include_directories(_core PRIVATE src)
install(TARGETS _core DESTINATION ahl_dwc)
```

`PYBIND11_MODULE(_core, m)` (`src/bindings.cpp:62-69`) registers five symbols: the three
`adult_weight_wrapper*` entry points, `EnergyBuilder` and `set_seed`.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| setuptools + `setup.py` with a hand-written `Extension` | No evidence in any commit that it was tried; there is no `setup.py` in the history. scikit-build-core removes the need to hand-roll compiler flags and wheel tags, and gives PEP 517 isolation for free. Record as "no alternative recorded". |
| meson-python, Cython, nanobind | No repo evidence either way. pybind11 was the implicit choice because the shim mirrors Rcpp's value semantics onto pybind11 casts (`src/shim.hpp:60-66`, `src/bindings.cpp:11-12`). |
| Vendoring prebuilt binaries | Would defeat the point of building from upstream sources and would not be installable across platforms. |

## Consequences

Positive:

- One short, readable build file; nothing bespoke to maintain.
- PEP 517 build isolation means a plain `uv sync` or `pip install .` fetches `scikit-build-core` and
  `pybind11` itself, and scikit-build-core will pull `cmake`/`ninja` wheels if the system CMake is
  unsuitable.
- `build.verbose = true` and `logging.level = "INFO"` (`pyproject.toml:5-7`) put the CMake configure
  and compile lines in the output, so build failures are diagnosable without re-running.

Negative:

- **The build requirements are not pinned anywhere.** Neither `scikit-build-core` nor `pybind11`
  appears in `uv.lock` (verified), so both resolve fresh at every build. A pybind11 major bump can
  break the build with no change in any committed file. For a compiled package this is the largest
  single reproducibility gap.
- **No C++ standard is specified.** `CMakeLists.txt` sets no `CMAKE_CXX_STANDARD`, and pybind11's
  exported CMake targets propagate no `cxx_std_*` compile feature (verified: no `cxx_std` in the
  installed `pybind11/share/cmake/pybind11/*.cmake`). The effective standard is the compiler default
  — which varies by toolchain, and toolchain divergence has already broken the build once (ADR 0007).
- **No optimisation or floating-point flags are set**, so numerical results depend on the build's
  default optimisation level and FMA contraction. This is why the regression tolerance in ADR 0006 is
  loose rather than exact.
- Every install without a matching wheel needs a compiler and CMake ≥ 3.15 (ADR 0008).
- Marshalling is by value: pybind11's `stl.h` copies the `std::vector` arguments, and
  `to_mat`/`to_vec` (`src/bindings.cpp:11-12`) copy again into the shim types. Every call copies its
  inputs twice.
- No build directory is retained, so an incremental C++ edit costs a full CMake reconfigure.
- `_core` is not committed and has no type stub, so editors and type-checkers see nothing for the
  extension (`ahl_dwc/__init__.py:4` `from . import _core`).

## Evidence

- `76246e0` (2025-11-20) adds `CMakeLists.txt` and the `[build-system]` table.
- `pyproject.toml:1-3` (backend), `:5-7` (scikit-build options).
- `CMakeLists.txt:1-13`.
- `src/bindings.cpp:11-12` (copying helpers), `:62-69` (module definition).
- `75b1c37` / PR #3 renames the CMake project and install destination as part of
  `ahl_hall_model_py` → `ahl_dwc`.
