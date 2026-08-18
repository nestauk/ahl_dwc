---
status: accepted
date: 2025-11-20
deciders: Harry Wilde (HarrisonWilde)
---

# 0001. Wrap upstream `bw`'s C++ rather than reimplement or shell out to R

## Context

Nesta's A Healthy Life mission needed Hall et al.'s dynamic weight-change model callable from
Python analysis code. The reference implementation is the R package
[INSP-RH/bw](https://github.com/INSP-RH/bw), whose numerical core is already C++ called through
Rcpp. Three routes were open: reimplement the model in Python, call R from Python at runtime, or
compile the existing C++ directly into a Python extension.

The model is a coupled ODE system integrated with RK4 over four state variables
(`src/adult_weight.cpp:446-577`). Reimplementing it means owning the numerics — and owning the
burden of proving numerical equivalence with the published reference.

## Decision

We compile the upstream `bw` C++ sources into a Python extension module `_core` and expose a thin
Python marshalling layer on top. `ahl_dwc/__init__.py` normalises inputs (sex string to `1.0`/`0.0`,
tiling and transposition of `ei_change`/`na_change` into the C++ column layout) and dispatches to
one of three C++ entry points. The scientific core is not rewritten.

Only `adult_weight` and `energy_build` are exposed. `child_weight` is deliberately out of scope
(issue #4, open: "Might become relevant eventually if we fully migrate all of our analysis to
python").

## Alternatives considered

| Alternative                                                            | Why not chosen                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reimplement the model in Python/NumPy                                  | Would require independently validating a published physiological model. A partial attempt existed — `ahl_hall_model_py/model.py` (98 lines, added in `02ace3b`) reimplemented the _input normalisation_ in Python and is full of in-line uncertainty about the row/column orientation of `EIchange` ("Wait, looking at C++: …"). It was deleted in `f10d469` and folded into the package `__init__`. Only the marshalling was ever attempted in Python; the numerics never were. |
| Call R from Python (`rpy2`, subprocess)                                | No repo evidence this was evaluated — record this as "no alternative recorded" rather than "rejected". It would have made R plus the `bw` package a hard runtime dependency of every consumer.                                                                                                                                                                                                                                                                                   |
| Keep the Nesta DS cookiecutter structure and add the model as a module | The cookiecutter skeleton (`0194747`, 19:50) was replaced wholesale 54 minutes later (`76246e0`, 20:44): `ahl_hall_model/{__init__,analysis,getters}`, `outputs/`, README and LICENCE deleted, C++ sources added. `.envrc` and `.pre-commit-config.yaml` are the only surviving cookiecutter artefacts.                                                                                                                                                                          |

## Consequences

Positive:

- The numerical core is the published reference implementation. No equivalence proof is needed for
  the model itself, only for the marshalling.
- Performance is native C++; whole populations advance as vectors in lockstep.
- Upstream fixes can, in principle, be pulled in by copying files.

Negative:

- **We do not own the scientific core.** Upstream bugs are inherited wholesale, and the repo has no
  mechanism to detect upstream change — no submodule, no vendoring manifest, no recorded upstream
  commit or version.
- Known upstream defects ship as-is. `Correct_Values` is dead: the finiteness check it exists for is
  entirely commented out (`src/adult_weight.cpp:488-496`), leaving an empty loop, so the
  `checkValues=True` hard-coded at `ahl_dwc/__init__.py:87,105,121` buys nothing.
- The Python layer performs no validation of its own. `n_ind` is taken from `bw` alone
  (`ahl_dwc/__init__.py:43`); a length mismatch against `ht`/`age`/`sex` is an out-of-bounds heap
  read, not an exception (reproduced: returns `[80., nan, nan, nan]` with no error).
- Unknown `sex` strings silently become male (`ahl_dwc/__init__.py:42`); unknown `**kwargs` are
  silently discarded (`ahl_dwc/__init__.py:68-70`), so a `PAL`/`pal` casing slip changes results by
  hundreds of kcal with no signal.
- Every install requires a C++ toolchain unless a matching wheel exists (see ADR 0008).
- `child_weight` remains unavailable; adding it means another wrapper and more shim surface.

## Evidence

- `0194747` (2025-11-20 19:50) cookiecutter skeleton; `76246e0` (20:44) "Working minimally" replaces
  it and adds `src/adult_weight.cpp` (589 lines), `src/adult_weight.h` (134), `src/bindings.cpp`
  (70), `src/shim.hpp` (267), `CMakeLists.txt`.
- `02ace3b` adds `ahl_hall_model_py/model.py`; `f10d469` deletes it. Both merged in PR #1
  (`e2f00cf`, 2025-11-20 21:28).
- `README.md:1-5`; `pyproject.toml:13` (description).
- `CMakeLists.txt:6-10` — `pybind11_add_module(_core src/bindings.cpp src/adult_weight.cpp src/energy_build.cpp)`.
- `ahl_dwc/__init__.py:38-122` — marshalling and three-way dispatch.
- Issue #4 (open) — `child_weight` deferred.
