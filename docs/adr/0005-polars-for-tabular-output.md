---
status: accepted
date: 2025-11-20
deciders: Harry Wilde (HarrisonWilde)
---

# 0005. Polars for the tabular output helper

## Context

`adult_weight` returns a dict of `(n_individuals, steps)` matrices plus a few scalars — convenient
for the C++ layer, awkward for analysis. Analysts want one long-format frame they can group, filter
and plot. That means picking a DataFrame library and taking it as a runtime dependency, because the
helper lives inside the package rather than in a downstream notebook.

## Decision

We add `results_to_polars(results) -> pl.DataFrame` and take **polars** as a runtime dependency.

The helper returns a long frame of `n_individuals * len(Time)` rows with columns `Time`,
`Individual_ID` and the ten time-series variables (`Body_Weight`, `Fat_Mass`, `Lean_Mass`,
`Glycogen`, `Extracellular_Fluid`, `Adaptive_Thermogenesis`, `Energy_Intake`, `Body_Mass_Index`,
`BMI_Category`, `Age`), hard-coded at `ahl_dwc/__init__.py:173-184`.

The same PR carried two other decisions worth naming: R-style `EIchange`/`NAchange` were renamed to
snake_case `ei_change`/`na_change` (`a361d9a`, "fix: pythonic kwargs"), and type hints were added and
corrected (`a8478ae`, `893c715`).

## Alternatives considered

| Alternative                                              | Why not chosen                                                                                                                                                                                                              |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pandas                                                   | **No comparison is recorded.** pandas appears in no commit in this repo's history. polars arrived in the same commit that first needed a frame. State this as "chosen without a visible evaluation", not "pandas rejected". |
| Return only NumPy arrays and leave framing to the caller | Would have avoided a runtime dependency entirely, and is the option this ADR would most likely revisit. Not evidenced as considered.                                                                                        |
| Optional extra (`ahl_dwc[polars]`) with a lazy import    | Not evidenced as considered; would keep the compiled core dependency-light.                                                                                                                                                 |

## Consequences

Positive:

- Analysts get a plot-ready long frame in one call, with a shape contract that is tested
  (`tests/unit/test_api.py:90` `test_results_to_polars_returns_long_dataframe`; the ten keys are
  pinned at `tests/unit/test_api.py:19-30`).
- polars is fast and dependency-light relative to pandas, and is already common in Nesta analysis
  code.

Negative:

- **polars is a hard runtime dependency of a package whose value is the compiled extension**
  (`pyproject.toml:17`). Consumers pay for it whether or not they ever call `results_to_polars` —
  including in constrained environments where the point of the package is the ODE solver.
- The helper is brittle by construction: the ten keys are hard-coded, so any result dict missing one
  raises `KeyError` rather than degrading.
- It relies on C row-major `ravel()` ordering matching `np.tile`/`np.repeat`
  (`ahl_dwc/__init__.py:201-212`). Correct today, but an unstated invariant.
- Two frame libraries in one workflow: analysts using pandas elsewhere must convert.
- The API is now inconsistent in its return types — `adult_weight` hands back a dict mixing NumPy
  arrays with Python lists (`Time`, `BMI_Category`), and `results_to_polars` is the only thing that
  smooths that over. `examples/reproduce_bw_vignette.py:36,43,123` indexes `res["Body_Weight"]` with a
  NumPy tuple index directly, which is exactly the inconsistency a new contributor trips on.

## Evidence

- `0c08b37` (2025-11-20 23:42) "feat: add function to place appropriate parts of output into a df" —
  adds `polars>=1.8.2` to `[project] dependencies` and +158 lines to the package `__init__`. Merged
  as PR #2 (`01398e8`).
- `a361d9a`, `a8478ae`, `893c715` — kwargs rename and type hints in the same PR.
- `ahl_dwc/__init__.py:2` (`import polars as pl`), `:159` (signature), `:173-184` (the ten keys),
  `:201-212` (ravel/tile/repeat).
- `pyproject.toml:17` — `dependencies = ["numpy>=1.24.4", "polars>=1.8.2"]`.
- `tests/unit/test_api.py:90`.
