---
status: accepted
date: 2026-07-09
deciders: Solomon Yu (sqr00t)
---

# 0006. Test strategy: unit/regression split, `PHYS_RTOL = 1e-4`, Brownian pinned by seed only

## Context

The repo had no tests at all until 2026-07-09. That was tolerable while the only consumer was its
author, and untenable the moment a C++ source change was proposed (ADR 0007) — there was no way to
show the fix preserved behaviour.

Two properties of this package constrain any test design:

1. The numerics are upstream code we do not own (ADR 0001). We cannot test the model's _correctness_
   against a specification we did not write; we can only pin its _behaviour_ and detect change.
2. Results are not bit-reproducible across platforms. The integration path is `double` arithmetic
   over `std::exp`, `std::log`, `std::pow`, and `CMakeLists.txt` sets neither an optimisation level
   nor a floating-point model (ADR 0003), so libm accuracy and FMA contraction differ per toolchain.
   And `std::normal_distribution` is implementation-defined, so the Brownian path differs between
   libstdc++ and libc++ for the same seed.

## Decision

Split the suite by what each test can honestly assert.

**`tests/unit/`** — the Python marshalling layer: shapes, dispatch, argument handling, validation
errors, the `results_to_polars` contract. No golden numbers. Seven test functions in
`tests/unit/test_api.py`, parameterised.

**`tests/regression/`** — the compiled extension's numerical behaviour, pinned four different ways
depending on what is defensible:

| What                                   | How it is pinned                                                      | Why that tolerance                                                                                                                                                                                                                                              |
| -------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Model output under a sustained deficit | Golden final `Body_Weight` at `rtol = PHYS_RTOL = 1e-4`               | "Loose enough for cross-platform libm/FMA differences, tight enough that a real model regression (order 0.1 kg+) fails" (`tests/regression/test_adult_weight.py:14-16`). The module docstring adds that genuine regressions "shift results by whole kilograms". |
| No intake change                       | `atol=1e-6` against 80.0 (`tests/regression/test_adult_weight.py:38`) | Analytically exact — weight must not move — so it is pinned tightly.                                                                                                                                                                                            |
| `energy_build` Linear                  | `rtol=1e-9` (`tests/regression/test_energy_build.py:21`)              | Analytic straight-line interpolation; no accumulation of floating-point error to absorb.                                                                                                                                                                        |
| `energy_build` Brownian                | **Seed-reproducibility and seed-variance only** — no values           | `std::normal_distribution` "is implementation-defined and its exact values are not portable across standard libraries" (`tests/regression/test_energy_build.py:4-7`). Two tests: same seed gives identical output, different seed gives different output.       |

Four golden final weights are captured "from the reference build"
(`tests/regression/test_adult_weight.py:23-32`), covering all three C++ entry points:

| Scenario                                                   | Expected final `Body_Weight` (kg) |
| ---------------------------------------------------------- | --------------------------------- |
| `female_deficit`                                           | 73.178765                         |
| `male_deficit`                                             | 83.194082                         |
| `ei_variant` (exercises `adult_weight_wrapper_EI`)         | 85.140406                         |
| `ei_fat_variant` (exercises `adult_weight_wrapper_EI_fat`) | 85.154781                         |

Tests are exempted from annotation and docstring lint —
`"tests/**" = ["ANN", "D100", "D103"]` with the rationale "Tests don't need type annotations or
module/function docstrings" (`pyproject.toml:73-74`).

Present state: 15 test functions across three files, parameterised to about 30 collected;
`uv run pytest -q` gives 30 passed in 0.22 s.

## Alternatives considered

| Alternative                                                                                        | Why not chosen                                                                                                                                                                                          |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bit-exact golden values everywhere                                                                 | Impossible across the CI matrix — the Linux and macOS legs use different standard libraries and libm implementations. Would produce failures that mean nothing.                                         |
| No golden values, property-based assertions only (weight falls under a deficit, mass is conserved) | Too weak: a change that shifted every trajectory by a constant would pass. `test_calorie_deficit_causes_weight_loss` exists, but as a complement, not a replacement.                                    |
| Pin Brownian values with a fixed seed                                                              | Rejected on evidence: those values are not portable across standard libraries, so the test would fail on whichever OS was not used to capture them.                                                     |
| Compare against upstream R `bw` output as the oracle                                               | Would be the strongest check, and is **not** implemented. There is no committed comparison script and no record of which toolchain produced the goldens — see the negative consequences.                |
| A single flat `tests/` directory                                                                   | Was the original shape (`tests/test_unit.py`, `tests/test_regression.py`, both added in `bf87e07`); reorganised in `a85cd27` once regression coverage grew enough to warrant a file per model function. |

## Consequences

Positive:

- The suite guards the thing it can actually guard — behaviour change — and says so in its own
  docstrings, so nobody mistakes it for a validation of the model.
- Tolerances are per-assertion and justified in the file, not one global fudge factor.
- Coverage now reaches all three `adult_weight` dispatch paths; the `EI` and `EI_fat` wrappers were
  untested before `a85cd27`.
- It is fast (0.22 s), so it runs on every leg of a 15-environment matrix without cost.

Negative:

- **The provenance of the golden values is unrecorded.** The docstring says "captured from the
  reference build", but there is no committed capture script, no comparison against upstream R `bw`
  output, and no record of the machine or toolchain. If they were captured from a build with a bug,
  the suite pins the bug.
- `PHYS_RTOL = 1e-4` on an ~80 kg value tolerates roughly 8 g of drift. A real but small regression —
  a changed constant that moves results by 50 g — passes.
- **Brownian is effectively untested for correctness.** Seed-reproducibility and seed-variance would
  both hold for an implementation that returned nonsense.
- The goldens bake in known upstream quirks, including the off-by-one horizon: `days=365, dt=1.0`
  gives 365 columns with `Time[-1] == 364.0`. Fixing that quirk would require re-capturing every
  golden.
- **No test or example passes `pal`, `pcarb` or `pcarb_base`** (verified by grep over `tests/` and
  `examples/`). The `pcarb`/`pcarb_base` argument order flips across three layers
  (`ahl_dwc/__init__.py:81-82` → `src/bindings.cpp:18,23` → `src/adult_weight.cpp:121-122`); it is
  correct today, but both default to `0.5`, so a swap would be invisible to the suite.
- Nothing tests the undefined-behaviour paths (mismatched input lengths, non-broadcast scalar
  `ei`/`fat`) — they return `NaN` silently, so a test would have to assert on UB.
- Nothing exercises Python 3.8 or 3.9 (ADR 0004, ADR 0007), on which the package does not import.

## Evidence

- `bf87e07` (2026-07-09) adds `tests/test_unit.py` (99 lines) and `tests/test_regression.py` (67) in
  the same commit as the C++ fix, plus `[tool.pytest.ini_options] testpaths = ["tests"]`,
  `pytest>=7.0` in the dev group, and the tests per-file lint ignore.
- `a85cd27` (2026-07-23) "test: reorganise into unit/ + regression/, parameterise, cover EI variants".
- `tests/regression/test_adult_weight.py:1-7` (docstring), `:14-16` (`PHYS_RTOL`), `:23-32`
  (goldens), `:38` (`atol=1e-6`), `:56-59` (determinism).
- `tests/regression/test_energy_build.py:1-7` (portability rationale), `:21` (`rtol=1e-9`),
  `:31-44` (seed tests).
- `tests/unit/test_api.py:19-30`, `:90`.
- `pyproject.toml:47-48` (pytest), `:73-74` (tests lint ignore).
