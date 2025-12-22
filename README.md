# Hall's Dynamic Weight Change (DWC) model - `bw` Python wrapper

This is a python wrapper of the [bw](https://github.com/INSP-RH/bw) package's C++ implementation of the [Dynamic Weight Change model from Hall et al.](https://www.niddk.nih.gov/research-funding/at-niddk/labs-branches/LBM/integrative-physiology-section/research-behind-body-weight-planner/Documents/Hall_Lancet_Web_Appendix.pdf) for adults.

Specifically, this package provides Python bindings via C++ shimming for the `adult_weight` and `energy_build` functions. See the original package for comprehensive documentation.

## Installation

You can install the package via `uv`:

```bash
uv add git+https://github.com/nestauk/ahl_dwc.git --tag v0.1.0
```

Or develop locally by cloning the repo and running `uv sync`.

## Implementation Details

- `shim.hpp` contains the necessary shims to replace Rcpp functionality with standard C++ and pybind11 equivalents, this is entirely new code.
- `bindings.cpp` contains the pybind11 bindings for the two functions we are exposing, this is entirely new code.
- `adult_weight.cpp` is identical to the version in the `bw` package.
- `adult_weight.h` has been modified very slightly to use `shim.hpp` (the main new code in `src`) to replace the references to `math.h` and `Rcpp.h` in the original version. The actual structure of `adult_weight.h` is near identical to the original though.
- `energy_build.cpp` is identical to the version in the `bw` package.
