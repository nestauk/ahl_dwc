---
status: accepted
date: 2025-11-20
deciders: Harry Wilde (HarrisonWilde)
---

# 0002. Isolate Rcpp behind `shim.hpp` and keep the model sources unchanged

## Context

ADR 0001 committed us to compiling upstream `bw`'s C++ into a Python extension. That code is written
against Rcpp: it uses `Rcpp::NumericVector`, `Rcpp::NumericMatrix`, the `_` slice sentinel,
vectorised arithmetic operators, `Rcpp::Named`/`List::create`, `R::rnorm` and `Rcout`. Rcpp is an R
API and cannot be linked into a Python extension.

Two ways to remove that dependency: edit the model sources to use pybind11 and std C++ directly, or
provide a header that reimplements the Rcpp surface the model needs so the sources compile unchanged.

## Decision

We write one new header, `src/shim.hpp`, that reimplements the Rcpp surface in standard C++ plus
pybind11, and we leave `src/adult_weight.cpp` and `src/energy_build.cpp` as the upstream code.
`src/adult_weight.h` is changed only to include `shim.hpp` instead of `math.h` and `Rcpp.h`.
`src/bindings.cpp` is the other new file: the pybind11 module definition.

`shim.hpp` includes only `<vector> <string> <cmath> <algorithm> <iostream> <random>` and pybind11
headers — no `Rcpp.h`. What it provides:

| Rcpp construct | Shim replacement | Location |
|---|---|---|
| `NumericVector` | `class NumericVector : public std::vector<double>` with `operator()` and implicit `py::object` conversion | `src/shim.hpp:46-66` |
| Vectorised `+ - * /` | `DEF_OP` macro over `std::plus`/`minus`/`multiplies`/`divides` | `src/shim.hpp:105-113` |
| `pow`, `exp`, `log` | element-wise free functions | `src/shim.hpp:115-135` |
| `NumericMatrix` | flat `std::vector<double>` + `rows`/`cols`, row slice by value, column proxy | `src/shim.hpp:138-204` |
| `Rcpp::_` | empty `struct Slice`, `static const Slice _` | `src/shim.hpp:15-18` |
| `StringVector`/`StringMatrix` | `std::vector<std::string>` wrappers | `src/shim.hpp:207-246` |
| `Named(...)`, `List::create(...)` | `NamedBuilder` + variadic `List::create` over `py::dict` | `src/shim.hpp:249-286` |
| `R::rnorm` | `std::normal_distribution` over a shared `std::mt19937` | `src/shim.hpp:22-43, 69-74` |
| `Rcout` | `#define Rcout std::cout` | `src/shim.hpp:288` |

### Sub-decision: process-wide RNG with an exposed `set_seed`

The first version of the shim gave `rnorm` a function-local `static std::mt19937 gen(42)` — "Fixed
seed for reproducibility in vignette". `02ace3b` replaced that with a singleton `get_rng()` seeded
from `std::random_device`, plus an exposed `set_seed(int)` and a `fill_rnorm()` writing into a raw
pointer. Stated rationale in the source: "Singleton pattern for the generator so it's shared across
all C++ files." Consequence: `set_seed` is part of the public Python API, and Brownian output is
reproducible only within a process and only after an explicit `set_seed`.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Rewrite the model sources against pybind11 directly | Every future upstream change would then have to be re-applied by hand against a diverged file, and any numerical difference would be ours to explain. Keeping the sources unchanged makes a regression attributable to the shim or the bindings, never to the model. |
| Depend on Rcpp headers without R | Rcpp's types are bound to R's memory model (`SEXP`, protection stack); there is no header-only subset that works outside R. |
| Rewrite the model in terms of Eigen/xtensor and drop the R idioms | Same objection as the first row, plus a new third-party dependency. Not evidenced as considered. |

## Consequences

Positive:

- One file carries every R-semantics assumption. A porting bug has one plausible home.
- The model sources can be diffed against upstream to check for drift.
- The abstraction is small (288 lines) and dependency-free beyond the standard library and pybind11.

Negative:

- **The "identical to `bw`" claim in `README.md` is about code, not bytes.** `75b1c37` (2025-12-22)
  re-added upstream's MIT header comments to `src/adult_weight.h` (+28 lines) and
  `src/energy_build.cpp` (+39) and restored an upstream comment on `double K = 5000` — i.e. the files
  had already drifted in comments and were brought back toward upstream later. `src/energy_build.cpp`
  also necessarily differs in its includes (`#include "shim.hpp"`). Read the claim as "identical in
  code, drifted in comments".
- **Unchanged upstream sources cannot be reformatted**, so `clang-format --style=Google` can never be
  made blocking on them without abandoning this ADR. That is exactly why the `cpp` job in
  `.github/workflows/format.yml:30` is `continue-on-error: true`. Compiler warnings in upstream code
  (e.g. the signed/unsigned comparison at `src/adult_weight.cpp:422`) are likewise left alone.
- **The shim is a single point of portability failure**, and it has already failed once — see
  ADR 0007 and `src/shim.hpp:49-55`.
- **No bounds checking anywhere.** `NumericVector::operator()` forwards to
  `std::vector::operator[]` (`src/shim.hpp:58-59`), and the binary operators size the result from the
  left operand only. Mismatched lengths read past the end of the heap — undefined behaviour, not an
  exception (see ADR 0001's Consequences).
- **Asymmetric slice semantics.** `m(r, _)` returns a row by value and silently yields zeros for an
  out-of-range row (`src/shim.hpp:186-193`); `m(_, c)` returns a mutable proxy holding
  `NumericMatrix&` with no range check (`src/shim.hpp:163, 195`). A silent zero-fill converts an
  indexing bug into wrong numbers rather than a crash, and the proxy is a dangling-reference hazard
  that is safe only because every call site consumes it immediately.
- Inheriting publicly from `std::vector` (`src/shim.hpp:46, 207`) gives no virtual destructor — safe
  here only because nothing deletes through a base pointer.
- The comment at `src/shim.hpp:177` advertises `+=` support that is not implemented.
- The RNG is a lock-free process-global mutated without releasing the GIL; that, and nothing else, is
  why it is currently thread-safe. Its default seeding is `std::random_device`, so Brownian output is
  non-reproducible across processes unless `set_seed` is called.
- `std::normal_distribution` is implementation-defined, so identical seeds give different Brownian
  paths across standard libraries. This directly constrains the test strategy (ADR 0006).

## Evidence

- `76246e0` (2025-11-20) adds `src/shim.hpp` (267 lines); `02ace3b` (21:15) extends it and replaces
  the fixed-seed static RNG with the singleton + `set_seed`.
- `75b1c37` (2025-12-22, PR #3) re-adds upstream MIT headers and comments.
- `src/shim.hpp:1-11` (includes), `:15-18`, `:22-43`, `:46-66`, `:105-135`, `:138-204`, `:249-288`.
- `README.md` "Implementation details" table — which files are new and which are upstream.
- `.github/workflows/format.yml:29-38` — non-blocking clang-format/cppcheck.
