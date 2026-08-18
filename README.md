# ahl_dwc — Hall dynamic weight change model for Python

`ahl_dwc` runs the **Hall et al. dynamic weight change (DWC) model**: given a person's starting weight, height, age and sex, plus a change in daily energy intake (and optionally sodium intake), it simulates their body-weight trajectory day by day — fat mass, lean mass, glycogen, extracellular fluid, adaptive thermogenesis, energy intake, BMI and BMI category. It is a Python wrapper around the C++ implementation in the R package [`INSP-RH/bw`](https://github.com/INSP-RH/bw), so you get the same numerics without leaving Python.

It is built for **Nesta A Healthy Life (`ahl_`) analysts** modelling body-weight trajectories under changed energy or sodium intake — for example, estimating the weight effect of a reformulation or retail intervention across a population. Reference for the model itself: [Hall et al., _Lancet_ web appendix](https://www.niddk.nih.gov/research-funding/at-niddk/labs-branches/LBM/integrative-physiology-section/research-behind-body-weight-planner/Documents/Hall_Lancet_Web_Appendix.pdf).

Two `bw` functions are exposed — `adult_weight` and `energy_build`. The child model is not wrapped (see [issue #4](https://github.com/nestauk/ahl_dwc/issues/4)).

## Install

From the git tag (works everywhere; builds the extension locally):

```bash
uv add git+https://github.com/nestauk/ahl_dwc.git --tag v0.1.0
```

From Nesta's private CodeArtifact PyPI, once your shell is authenticated to it (the index URL is not published in this repo — it lives in GitHub secrets because the repo is public):

```bash
uv add ahl_dwc
```

Whether `0.1.0` is actually present in CodeArtifact is not confirmed from this repo: the tag predates the publish workflow by seven months, and the only recorded successful upload is the macOS wheel from the PR #8 test run ([issue #9](https://github.com/nestauk/ahl_dwc/issues/9), which also records a 409 on a pre-existing `0.1.0` sdist). Prefer the git-tag install unless you have checked the index.

The publish workflow builds on a single Linux runner, so the only prebuilt wheel it can produce is **linux/x86_64**; on macOS, Linux arm64 or Windows you will build from the sdist and need a C++ compiler and CMake ≥ 3.15. Local development is `git clone` then `uv sync`.

## Quickstart

```python
from ahl_dwc import adult_weight, energy_build, results_to_polars

# Ramp a 250 kcal/day deficit in linearly over 180 days, then hold it to day 365.
ei = energy_build([0.0, -250.0, -250.0], [0, 180, 365], "Linear")   # shape (1, 365)

res = adult_weight(
    bw=[80.0], ht=[1.8], age=[40.0], sex=["female"],
    ei_change=ei[0], days=365,
)
print(res["Body_Weight"][0, -1])        # 74.395... kg
df = results_to_polars(res)             # long-format Polars frame, 365 rows x 12 cols
```

## API

Four public names, all in `ahl_dwc/__init__.py`.

| Function                                                                                             | Purpose                                                                                               | Key parameters                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `adult_weight(bw, ht, age, sex, ei_change=None, na_change=None, days=365, dt=1.0, **kwargs) -> dict` | Simulate adult weight trajectories for one or more individuals                                        | `bw` kg, `ht` m, `age` years, `sex` `"female"`/`"male"`; `ei_change` (kcal/day) and `na_change` (sodium) deltas (scalar-per-day series, tiled across individuals, or one row per individual); `days` horizon, `dt` step in days. `**kwargs`: `pal` (1.5), `pcarb` (0.5), `pcarb_base` (0.5), `ei` (baseline kcal), `fat` (baseline fat mass kg) |
| `energy_build(energy, time, interpolation="Brownian") -> np.ndarray`                                 | Interpolate control points into a daily energy-change series suitable for `ei_change`                 | `energy` values at `time` days (`time[0]` must be `0`); `interpolation` ∈ `Linear`, `Exponential`, `Stepwise_R`, `Stepwise_L`, `Logarithmic`, `Brownian`                                                                                                                                                                                        |
| `results_to_polars(results) -> pl.DataFrame`                                                         | Flatten an `adult_weight` dict to a long frame: `Time`, `Individual_ID`, plus ten time-series columns | the dict returned by `adult_weight`                                                                                                                                                                                                                                                                                                             |
| `set_seed(seed: int)`                                                                                | Seed the process-global C++ RNG                                                                       | only affects `energy_build(..., "Brownian")`; `adult_weight` is deterministic                                                                                                                                                                                                                                                                   |

`adult_weight` returns a dict: `Time` and `BMI_Category` are Python lists; `Age`, `Adaptive_Thermogenesis`, `Extracellular_Fluid`, `Glycogen`, `Fat_Mass`, `Lean_Mass`, `Body_Weight`, `Body_Mass_Index` and `Energy_Intake` are `(n_individuals, steps)` NumPy arrays; plus `Correct_Values` (bool) and `Model_Type` (`"Adult"`).

### Sharp edges worth knowing before you trust a result

These are inherited from the upstream C++ and are documented rather than fixed. See `docs/runbooks/` for the detail.

- **`adult_weight` does not validate its inputs.** `n_individuals` is taken from `bw` alone; a shorter `ht`/`age`/`sex` reads past the end of the buffer — undefined behaviour that in practice returns `NaN` rather than raising. Unknown `**kwargs` are silently dropped (`PAL` is not `pal`). A `sex` string other than `"female"` is treated as male. `energy_build` is the exception: it raises `ValueError` if `energy` and `time` disagree in length, if `time[0]` is not `0`, or if any time is negative — but an unrecognised `interpolation` string is silently ignored rather than rejected: every column stays at its initialised `0.0` except the last, which is unconditionally overwritten with the final `energy` value (`src/energy_build.cpp:81-118`). So the result is not all-zero, and cannot be detected with an all-zero check.
- **`ei_change` sets the horizon.** If the forcing array is shorter than `days`, the run is silently truncated to its length.
- **`days` is one step short.** `days=365, dt=1.0` gives 365 columns with `Time[-1] == 364.0`.
- **Brownian output is not portable.** `std::normal_distribution` is implementation-defined, so the same seed gives different paths on libstdc++ and libc++; without `set_seed` it differs between processes.

## How it works

```
your call  ->  ahl_dwc/__init__.py            marshalling: sex -> 1.0/0.0, tile and
                                              transpose ei_change/na_change to the
                                              C++ column layout, broadcast pal/pcarb
           ->  one of three C++ wrappers      chosen by which kwargs you passed:
                 adult_weight_wrapper           neither ei nor fat  -> everything estimated
                 adult_weight_wrapper_EI        exactly one of them
                 adult_weight_wrapper_EI_fat    both
           ->  Adult::rk4()                   RK4 over adaptive thermogenesis,
               (src/adult_weight.cpp)         extracellular fluid, glycogen and lean
                                              mass; fat mass is algebraic, body weight
                                              is reconstructed from the four states
```

`energy_build` is a separate, simpler path: `_core.EnergyBuilder` interpolates the control points, and the Python layer drops the day-0 column so the result lines up with `adult_weight`'s steps.

## Supported platforms and Python versions

|              | Status                                                                                                                                                                                                                                    |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python       | Tested on **3.10–3.14** (tox matrix in `pyproject.toml`, run by `tests.yml`). `requires-python` says `>=3.8`, but the package uses PEP 604 unions in runtime signatures and **will not import on 3.8/3.9** — treat 3.10 as the real floor |
| Linux x86_64 | Tested in CI; the only prebuilt wheel                                                                                                                                                                                                     |
| Linux arm64  | Tested in CI (`ubuntu-24.04-arm`); build from sdist                                                                                                                                                                                       |
| macOS        | Tested in CI (`macos-latest`, Apple Clang); build from sdist                                                                                                                                                                              |
| Windows      | Not tested, no CI leg                                                                                                                                                                                                                     |

Building from source needs a C++ compiler and CMake ≥ 3.15. No C++ standard is pinned in `CMakeLists.txt`, so the compiler default applies.

## Implementation details

The porting strategy is to keep the scientific code unchanged and confine every R/Rcpp dependency to one new header.

| File                   | Status                                                                                                                                                                                                                                                                       |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/shim.hpp`         | **Entirely new.** Replaces the Rcpp surface the model uses — `NumericVector`, `NumericMatrix`, `StringVector`/`StringMatrix`, the `_` slice sentinel, `Named`/`List::create`, vectorised operators, and the RNG singleton behind `set_seed` — with standard C++ and pybind11 |
| `src/bindings.cpp`     | **Entirely new.** The pybind11 module `_core`: the three `adult_weight_wrapper*` entry points, `EnergyBuilder` and `set_seed`                                                                                                                                                |
| `src/adult_weight.cpp` | Upstream `bw` code, unchanged                                                                                                                                                                                                                                                |
| `src/energy_build.cpp` | Upstream `bw` code, with one added line — `#include "shim.hpp"` at `energy_build.cpp:38`                                                                                                                                                                                     |
| `src/adult_weight.h`   | Near-identical to `bw`; modified only to include `shim.hpp` in place of `math.h` and `Rcpp.h`                                                                                                                                                                                |

Because of this split, a numerical regression is attributable to the shim or the bindings rather than to the model. `_core` is built by CMake into `ahl_dwc/` and is not committed; there is no type stub, so editors see nothing for the extension.

## Documentation

| Where                                                                    | What                                                                                                                    |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| [`ONBOARDING.md`](ONBOARDING.md)                                         | Orientation for someone joining the work — architecture, setup, where to look first                                     |
| [`CONTRIBUTING.md`](CONTRIBUTING.md)                                     | Branch and commit conventions, what CI blocks on, how to add a regression test                                          |
| [`docs/adr/`](docs/adr/)                                                 | Architecture decision records — why the C++ is wrapped rather than reimplemented, why Polars, why CodeArtifact          |
| [`docs/runbooks/`](docs/runbooks/)                                       | Task-shaped guides: local build, release, diagnosing a failing CI leg                                                   |
| [`docs/ROADMAP.md`](docs/ROADMAP.md)                                     | Known gaps and planned work                                                                                             |
| [`docs/rust-port.md`](docs/rust-port.md)                                 | Assessment of replacing the C++ core with Rust + PyO3, and why the answer is currently no (ADR 0009)                    |
| [`examples/reproduce_bw_vignette.py`](examples/reproduce_bw_vignette.py) | Worked example reproducing the `bw` vignette (needs the `dev` group's matplotlib; writes PNGs to the working directory) |

For the model's own documentation — parameter meanings, the physiology, the published validation — read the [`bw` package](https://github.com/INSP-RH/bw) and the Hall et al. appendix.

## Licence and attribution

MIT — see [`LICENSE`](LICENSE). Copyright (c) 2025, Nesta.

`src/adult_weight.cpp`, `src/adult_weight.h` and `src/energy_build.cpp` are derived from [`INSP-RH/bw`](https://github.com/INSP-RH/bw), which is MIT licensed; the upstream copyright headers are retained in those files. The model is that of Hall et al.; this repository contributes only the Python bindings and the shim.
