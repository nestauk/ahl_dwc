# Assessment: porting the C++ core to Rust

Status: assessment only, and **its framing has since been overtaken**. Written against the worktree
at `fix/gcc-cpp-compat` (tip `2f46f9d`).

> **Read this first.** Every option below assumes the port would happen _in this repository_, and
> prices permanent divergence from upstream `bw` into the first day of work. That assumption no
> longer holds: a Rust port is being explored in a **separate repository**, so `ahl_dwc` pays none
> of that cost while it proceeds. The comparison below is still the right analysis of an _in-tree_
> port, and the recommendation for this repository is unchanged — but the live question has narrowed
> to _"under what conditions should `ahl_dwc` adopt an external implementation?"_. See
> [ADR 0009](adr/0009-evaluate-rust-pyo3-reimplementation.md).
>
> The part that survives intact is the safety net: no implementation, in-tree or out, is adoptable
> until the regression suite can tell you whether it is equivalent. That section is the one to act
> on.

The question this document was written to answer is whether `ahl_dwc` should replace its C++ core —
the ported `bw` model plus the hand-written Rcpp shim — with a Rust implementation exposed through
PyO3, instead of the current pybind11 + scikit-build-core + CMake chain.

Short answer: **not yet, and probably not on the current evidence.** The pain this repo actually
suffers is mostly build-and-distribution pain, which has a much cheaper fix. The single largest cost
of porting — losing the ability to pull upstream `bw` changes byte-for-byte — is not recoverable
once paid. The reasoning is below, with the conditions that would change the answer.

## Why consider it

Every item here is a real, recorded event in this repository, not a hypothetical.

| Pain                                                                                                                        | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A C++ overload-resolution difference between GCC/libstdc++ and Clang/libc++ broke all Linux builds while macOS stayed green | `bf87e07` "fix: remove duplicate NumericVector ctors for GCC compat"; the reasoning is preserved in-source at `src/shim.hpp:45-56`, and issue #7 records `-fpermissive` and `size_t` casts as tried and rejected                                                                                                                                                                                                                                                                                                                                                              |
| Stochastic output cannot be value-pinned, because `std::normal_distribution` is implementation-defined                      | `tests/regression/test_energy_build.py:1-7` says so explicitly; the Brownian path (`src/energy_build.cpp:56-70`) is therefore tested only for seed-reproducibility and seed-variance, never for values                                                                                                                                                                                                                                                                                                                                                                        |
| A hand-written 288-line Rcpp emulation layer sits under the whole model                                                     | `src/shim.hpp` — `NumericVector : public std::vector<double>` with `operator()` indexing (`:46-66`), a `DEF_OP` macro generating vector/scalar arithmetic (`:105-113`), a flat-buffer `NumericMatrix` with a `_` slice sentinel (`:15-18`, `:138-204`), and a `NamedBuilder`/`List::create` pair emulating `Rcpp::List` (`:249-286`). None of it bounds-checks; the binary operators size their result from the left operand only                                                                                                                                             |
| Wheels are built for one platform only, because cibuildwheel is not set up                                                  | `.github/workflows/publish-codeartifact.yml` header — a single `ubuntu-latest` runner, "If wheels for other platforms are needed, switch the build step to cibuildwheel". macOS, Linux arm64 and Windows consumers build from sdist and need a local toolchain                                                                                                                                                                                                                                                                                                                |
| ~~C/C++ formatting and static analysis are deliberately non-blocking~~ — **fixed, PR #21**                                  | Was `.github/workflows/format.yml` `cpp` job under `continue-on-error: true`, advisory "until a dedicated clang-format pass lands". That pass landed: clang-format is pinned and blocking over `shim.hpp` and `bindings.cpp`, with the upstream sources excluded by explicit file list ([ADR 0010](adr/0010-scope-clang-format-to-owned-sources.md)). `cppcheck` followed in PR #28: pinned to 2.17.1 and blocking too, over all of `src/`. Kept in this table because it was one of the five pains the port was argued to fix — and it was fixed without one, in about a day |

Two of these five (the shim and the RNG portability) are genuine language/ecosystem problems that a
Rust port would remove outright. Two (single-platform wheels, non-blocking C++ lint) are configuration
problems that a port would incidentally fix but that do not require one. One (the GCC divergence) is
already fixed, and its recurrence is now guarded by the two Linux legs of `.github/workflows/tests.yml`.

Since this was written, the non-blocking-lint pain has also been fixed outright, in about a day and
without a port (PR #21). That is worth stating plainly because it is evidence for the recommendation
below: the configuration problems really do yield to configuration fixes, so counting them as
motivation for a rewrite overstates the case for one.

Read honestly, the evidence supports "the C++ layer is fragile and under-tooled", not "the C++ layer
must be replaced".

## What the port would actually involve

### Size of the surface (verified line counts, this worktree)

| File                   |    Lines | Nature                                                                                                                                                                                                       |
| ---------------------- | -------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `src/adult_weight.cpp` |      589 | The model. Around 30 `Adult::` definitions: three constructors, three `build` overloads, parameter/RMR/steady-state setup, six derivative functions, `fatMass`, `R`, `BMIClassifier`, and `rk4` (`:446-577`) |
| `src/adult_weight.h`   |      162 | Class declaration plus upstream MIT header comments (re-added in `75b1c37`)                                                                                                                                  |
| `src/energy_build.cpp` |      123 | Six interpolation modes plus the Brownian bridge                                                                                                                                                             |
| `src/shim.hpp`         |      288 | The Rcpp emulation layer — **disappears entirely in a Rust port**                                                                                                                                            |
| `src/bindings.cpp`     |       69 | pybind11 module: three `adult_weight_wrapper*` entry points, `EnergyBuilder`, `set_seed`                                                                                                                     |
| **Total C++**          | **1231** | of which 357 (shim + bindings) is glue, 874 is model                                                                                                                                                         |
| `ahl_dwc/__init__.py`  |      215 | Python marshalling; largely survives, or shrinks if validation moves into Rust                                                                                                                               |

So the actual numerical translation job is roughly **870 lines of scientific C++**, not 1231. That is
small. It is also dense: `rk4` alone is 130 lines advancing four state matrices per step, with lean
mass using a staggered scheme that reuses already-advanced glycogen, adaptive thermogenesis and
extracellular fluid via midpoint averages (`src/adult_weight.cpp:532-537`). This is inherited upstream
behaviour, and it is exactly the kind of detail a careless rewrite "cleans up" and thereby breaks.

### Construct-by-construct mapping

| C++ today                                                                                   | Rust counterpart                                                                                             | Notes                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NumericVector` (`shim.hpp:46-66`)                                                          | `ndarray::Array1<f64>`                                                                                       | Element-wise arithmetic is native; the `DEF_OP` macro block (`:105-113`) has no analogue to write                                                                          |
| `NumericMatrix` + `ColProxy` (`shim.hpp:138-204`)                                           | `ndarray::Array2<f64>` with `.row()` / `.column_mut()`                                                       | `ndarray` over `nalgebra`: the model is element-wise vector maths on `nind x nsims` grids, not linear algebra. There are no matrix products anywhere in `adult_weight.cpp` |
| Unchecked `operator[]`, silent zero-fill for an out-of-range row slice (`shim.hpp:186-193`) | Bounds-checked indexing; an explicit `Result` on shape mismatch                                              | This removes a real defect class — see the length-mismatch out-of-bounds read recorded in the Consequences of [ADR 0001](adr/0001-wrap-upstream-bw-cpp.md)                 |
| `Adult` class, three constructors + three `build` overloads                                 | One struct plus a builder, or three constructor functions                                                    | The three entry points (`_wrapper`, `_wrapper_EI`, `_wrapper_EI_fat`, dispatched at `ahl_dwc/__init__.py:72-122`) become three constructors returning `Result`             |
| `rk4` returning `List` via `NamedBuilder` (`shim.hpp:249-286`, `adult_weight.cpp:564-576`)  | A `struct AdultResult` with named `Array2<f64>` fields, converted to a Python dict by PyO3 + `rust-numpy`    | Cleaner and typed; the Python-side dict contract consumed by `results_to_polars` (`ahl_dwc/__init__.py:173-184`) can stay identical                                        |
| `rnorm` over a process-global `std::mt19937` (`shim.hpp:22-43`), plus `set_seed`            | `rand` + `rand_distr::Normal` over an explicitly threaded `StdRng` (or a pinned `rand_pcg`/ChaCha generator) | The important win: pass the RNG in rather than keeping a mutable global. Values then become reproducible **across platforms**, which the C++ version cannot promise        |
| pybind11 + scikit-build-core + CMake (`CMakeLists.txt`, 13 lines)                           | PyO3 + maturin; `Cargo.toml` plus `build-backend = "maturin"`                                                | Removes the `find_package(pybind11 REQUIRED CONFIG)` failure mode and the unpinned build-time `pybind11`/`scikit-build-core` (neither appears in `uv.lock`)                |

One caveat on the RNG: `rand_distr::Normal` is _also_ not specified to be stable across versions of
`rand_distr`. Cross-platform reproducibility comes free; cross-_version_ reproducibility still requires
either pinning the crate exactly or vendoring the Box–Muller / ziggurat implementation. Do not sell
this as a solved problem — sell it as a problem that becomes solvable, which it currently is not.

## What "automatic" can and cannot do

Be blunt about this, because it is where these proposals usually get their optimism.

**c2rust does not apply.** It is a C-to-Rust transpiler. This is C++ with class inheritance
(`NumericVector : public std::vector<double>`), operator overloading (`operator()`, the `DEF_OP`
block), RAII, templates (`List::create` is variadic) and pybind11 template metaprogramming. c2rust
would not parse `src/adult_weight.cpp` at all. Even where it does work, its output is `unsafe`
raw-pointer transliteration that is harder to review than the original — which defeats the entire
purpose, since the only defensible reason to do this is to end up with _safer, more readable_ code.

**LLM-assisted porting is the realistic mechanism, and it is not automatic.** A plausible pipeline:

1. Port `src/shim.hpp` to nothing — delete it, and express its consumers in `ndarray` idiom by hand.
2. Port `src/energy_build.cpp` (123 lines, six branches, one stochastic path) function by function.
3. Port `adult_weight.cpp` in dependency order: parameter setup, then the six derivative functions,
   then `fatMass` / `R` / `BMIClassifier`, then `rk4` last.
4. Gate every single function behind a differential test against the C++ build (next section).

Where it will fail, specifically:

- **Silent semantic drift in the shim's R-isms.** `vector(n)` value-initialising to `0.0` stands in for
  R's zero-filled vectors; `m(r, _)` returns a zero vector for an out-of-range row. A translator
  producing "obviously better" Rust will turn the second into a panic or an error — correct in
  principle, but it changes behaviour, and no test currently says which behaviour is wanted.
- **The staggered RK4.** `adult_weight.cpp:532-537` looks like a bug to anyone who knows RK4. It is
  upstream's scheme. An LLM asked to "port this integrator" will very plausibly regularise it.
- **Index and off-by-one arithmetic.** `nsims = min(ceil(days/dt), EIchange.nrow() - 1.0)`
  (`adult_weight.cpp:453`) means `days=365` produces `Time[-1] == 364.0`, and the golden values in
  `tests/regression/test_adult_weight.py:23-32` bake that in. A "fixed" port fails every golden test
  for the right reason, and it will be tempting to re-baseline rather than investigate.
- **Forcing-term lookup, not interpolation.** `deltaEI(t) = EIchange(floor(t/dt), _)` (`:580-589`)
  means mid-step RK4 stages at `t + 0.5*dt` read the same row. Interpolating instead — the "obvious"
  improvement — changes every result.
- **Floating-point association.** Reordering an expression for readability changes the last digits.
  With `PHYS_RTOL = 1e-4` that is absorbed, but it destroys any hope of a bit-exact differential
  check, so the tolerance question has to be settled up front rather than discovered halfway through.

Realistic expectation: an LLM gets you 70–80% of a first draft quickly, and the remaining 20% is where
all the risk lives and where the calendar time goes.

## The safety net that makes it feasible

**The tests come before the port. This is the load-bearing point of the whole assessment.**

The current suite is 15 test functions (7 unit in `tests/unit/test_api.py`, 4 + 4 regression),
parameterised to 30 collected tests, with `uv run pytest -q` green. That is enough to catch a gross
regression and nowhere near enough to certify a rewrite. What it already gets right:

- `PHYS_RTOL = 1e-4` (`tests/regression/test_adult_weight.py:16`) with a stated rationale — loose
  enough for libm/FMA differences, tight enough that a real regression (order 0.1 kg) fails.
- Four golden final weights covering all three wrapper entry points (`:23-32`).
- An analytically exact tight pin wherever one is available (`Linear` at `rtol=1e-9`; the no-change
  baseline at `atol=1e-6` against 80.0).
- An explicit, reasoned refusal to value-pin Brownian (`tests/regression/test_energy_build.py:1-7`).

A Rust implementation is acceptable **iff** it reproduces the goldens within `PHYS_RTOL`. To make that
statement mean something, strengthen the suite first. This work is worth doing **whether or not the
port ever happens**, which is what makes it a safe first step.

1. **Broaden the golden set.** Four scenarios is thin for a four-state ODE system. Add goldens across:
   both sexes; extreme BMIs hitting all four `BMIClassifier` buckets (`adult_weight.cpp:422-441`);
   `dt = 0.5` and `dt = 0.25`; multi-individual runs (`n_ind > 1`), which no golden currently covers;
   and non-default `pal`, `pcarb`, `pcarb_base` — currently **no test or example passes any of the
   three**, so the known argument-order hazard between `ahl_dwc/__init__.py:81-82`, `src/bindings.cpp:18`
   and `adult_weight.cpp:121-122` is untested.
2. **Pin trajectories, not just endpoints.** Every golden is a final `Body_Weight`. Capture a full
   `(n_ind, steps)` array per scenario as an `.npz` fixture, plus the other nine series. A port that
   lands the right endpoint via a compensating pair of errors would pass today.
3. **Record provenance.** The docstring says goldens were "captured from the reference build" — there
   is no committed capture script and no record of the toolchain. Add
   `tests/regression/capture_goldens.py` and note the platform and compiler in the fixture. Without
   this there is no defensible answer to "is the golden wrong, or the port?".
4. **Property tests** (`hypothesis`), which are cheap and catch a different class of error:
   monotonicity (a sustained deficit never increases weight); the reconstruction identity
   `Body_Weight == Fat_Mass + Lean_Mass + Extracellular_Fluid + 3.7 * Glycogen`
   (`adult_weight.cpp:546`); `Body_Mass_Index == Body_Weight / ht^2` (`:549`); `ei_change = 0` implying
   a flat trajectory; shape invariants across all ten series.
5. **Differential testing, in one process.** The decisive tool. Build the Rust extension under a second
   module name (`ahl_dwc._core_rs`) alongside the existing `_core`, and run a randomised differential
   harness — sample valid inputs, call both, assert agreement within `PHYS_RTOL`, and for the
   deterministic `energy_build` modes assert something much tighter. Thousands of random cases beat any
   number of hand-written goldens. This is only possible while both implementations exist, which is an
   argument for the strangler strategy below.
6. **Settle Brownian first.** Decide now whether the port must reproduce C++ Brownian paths (it cannot —
   `std::normal_distribution` is unspecified) or is free to define new, cross-platform-stable ones. The
   second is the right answer, but it must be a stated decision rather than a discovered surprise,
   because it means Brownian output changes for existing users.

Estimate for items 1–4 alone: **4.5–7.5 engineer-days**, sized item by item as Phase 2 of
[`ROADMAP.md`](ROADMAP.md) (tasks 2.1–2.4), which is the canonical sizing for this work. They pay
for themselves regardless of the port
decision, and they are the prerequisite for taking any of the options below seriously.

## Migration strategies compared

Effort is engineer-days for one competent engineer with working Rust, including review. It excludes the
4.5–7.5 days of test hardening above, which every option should do first.

### (a) Full rewrite in one go

Port all 874 lines of model plus bindings; delete `src/`, `CMakeLists.txt` and the scikit-build-core
build; ship `ahl_dwc` from maturin.

- Effort: **15–25 days.** Rough shape: 3 for scaffolding (Cargo, maturin, PyO3, CI), 3 for
  `energy_build`, 8–12 for `adult_weight` and `rk4`, 4–6 chasing numerical discrepancies, 2 for
  release plumbing.
- Risk: **high.** One large diff on scientific code, with the upstream link severed on day one and no
  incremental point at which you can stop and still have something shippable. The tail is unbounded: a
  discrepancy at the fifth decimal in `rk4` can absorb a week on its own.

### (b) Strangler — port `energy_build` first, keep `adult_weight` in C++

Ship one wheel containing both `_core` (pybind11/C++) and `_core_rs` (PyO3/Rust).
`ahl_dwc/__init__.py` routes `energy_build` to Rust and `adult_weight` to C++.

- Effort: **6–9 days** for the first increment, of which around 3 is one-time dual-toolchain plumbing.
- Risk: **medium.** `energy_build` is the right first target: 123 lines, self-contained, no class
  hierarchy, already tested across all six modes, and it owns the only stochastic path — so porting it
  directly buys the cross-platform-reproducible Brownian that C++ cannot give. If it goes badly you
  delete one file and lose a week, not a quarter.
- The real cost is **not** the Rust: it is running maturin and scikit-build-core in one distribution.
  That is genuinely awkward. The options are a two-backend build glued by a custom build invocation, or
  shipping the Rust part as a separate internal dependency. Neither is free, and this overhead is why
  (b) is not obviously cheaper per unit of value than (a).
- It does, however, keep both implementations alive simultaneously, which is what makes the
  differential harness (item 5 above) possible at all.

### (c) Do not port — fix the actual pain directly

Three concrete changes:

1. **cibuildwheel.** Add `[tool.cibuildwheel]` and switch the build step in
   `publish-codeartifact.yml` (currently one `uv build` on `ubuntu-latest`) to a matrix producing
   manylinux x86_64 and aarch64, macOS x86_64 and arm64, and optionally Windows. This is the fix the
   workflow's own header already names. **2–3 days.**
2. **A pinned, portable normal distribution.** Replace `std::normal_distribution` in `shim.hpp:39` with
   an explicit Box–Muller or ziggurat implementation over the existing `std::mt19937` — which _is_
   specified and portable. Brownian output then becomes value-pinnable, and
   `tests/regression/test_energy_build.py` can gain real golden vectors. **1–2 days**, including
   re-baselining. Note this also changes existing Brownian output — the same one-off break as (a) and
   (b), for a fraction of the cost.
3. ~~**A checked-in `.clang-format` plus a repo-wide pass**, then drop `continue-on-error` from the
   `cpp` job.~~ **Done in PR #21, 1 day.** Delivered as a _scoped_ pass rather than a repo-wide one:
   only `shim.hpp` and `bindings.cpp` are formatted and checked, with the upstream sources excluded
   by explicit file list. The alternative floated here — pinning the exact upstream commit per
   vendored file and diffing in CI — was rejected on cost and remains the better answer if the
   number of vendored files grows. See [ADR 0010](adr/0010-scope-clang-format-to-owned-sources.md).
   Residual: none — `cppcheck` was pinned and made blocking in PR #28 (roadmap 3.4), so item 3
   is complete.

- Effort: **4–7 days total**, of which item 3 is now fully spent — **3–5 days remain**
  (cibuildwheel, and the portable normal distribution). Risk: **low.** Each item is independently
  shippable and independently revertible, which item 3 has now demonstrated in practice.
- What it does **not** fix: the shim stays, there is still no bounds checking, the build-time
  `pybind11`/`scikit-build-core` remain unpinned, and the next GCC-versus-Clang divergence is still
  possible — though CI now catches it.

### Recommendation

**Do (c) now. Do the test hardening alongside it.**

The clause that used to read "revisit (b) in six months" is superseded: (b) was a strategy for
porting _in this repository_, and the port is now being explored in a separate one. `ahl_dwc` does
not need to choose between (a), (b) and (c) at all — it does (c), and separately decides whether to
**adopt** whatever the external work produces. See
[ADR 0009](adr/0009-evaluate-rust-pyo3-reimplementation.md).

That makes the test hardening more important, not less. An external implementation is judged by
exactly one thing — whether it reproduces the golden values within `PHYS_RTOL` — and today there are
four golden endpoints to judge it against.

The reasoning is proportionality. Options (a) and (b) cost 15–25 and 6–9 days respectively and pay
their largest cost — upstream divergence — permanently and irreversibly. Option (c) costs 4–7 days and
resolves four of the five pains in the table above, leaving only "the shim is fragile" outstanding,
which is a maintainability concern rather than a live defect. Nothing in the recorded history shows the
shim causing a _user-visible_ problem; it caused one _build_ problem, which is fixed and guarded.

The test-hardening work is the part to be firm about. It is the only work item that is unambiguously
correct under every option, and without it neither (a) nor (b) can honestly be called verifiable.

## What would be gained and lost

### Gained

- **Cross-platform wheels become trivial.** `maturin` plus `PyO3/maturin-action` gives manylinux,
  macOS universal2 and Windows out of the box, replacing the single linux/x86_64 wheel of
  `publish-codeartifact.yml`. (cibuildwheel achieves the same for C++, at comparable effort.)
- **No shim.** 288 lines of `src/shim.hpp` deleted, along with every rough edge in it: unchecked
  `operator[]`, left-operand-sized binary operators, the silent zero-fill row slice, the `ColProxy`
  dangling-reference shape, and public inheritance from `std::vector` with no virtual destructor.
- **Memory safety by default.** The documented out-of-bounds heap read when `bw` and `ht` differ in
  length becomes a bounds-check panic or a typed `Err`, not undefined behaviour producing NaNs.
- **One toolchain.** `cargo` replaces "CMake ≥ 3.15, an unspecified C++ standard (`CMakeLists.txt` sets
  no `CMAKE_CXX_STANDARD`), and build-time `pybind11`/`scikit-build-core` that are absent from
  `uv.lock`". Rust's edition mechanism removes the compiler-defaults question entirely.
- **Enforceable formatting and lint.** `cargo fmt --check` and `cargo clippy -D warnings` can be
  blocking from day one, unlike the deliberately advisory `cpp` job.
- **Cross-platform reproducible randomness**, subject to the crate-version caveat above.

### Lost

- **The upstream link — this is the biggest cost and it is not recoverable.** Today
  `adult_weight.cpp` and `energy_build.cpp` are asserted to be the `bw` versions (README's
  "Implementation details" table),
  with only `adult_weight.h` "modified very slightly" for the shim include. Whatever the drift in
  comments (`75b1c37` re-added upstream MIT headers), the _code_ can still be diffed against
  INSP-RH/bw, and an upstream bug fix can be applied by copying a file. After a port, every upstream
  change requires a human to read R/C++ and re-implement it in Rust, forever. For a scientific model
  maintained by somebody else, that is a permanent recurring tax and the single strongest argument
  against porting.
- **Scientific-rewrite risk.** 874 lines of ODE integration, currently pinned by four golden endpoints.
  Even with a hardened suite, a subtle error that stays inside `PHYS_RTOL` on the tested scenarios and
  diverges elsewhere is a real possibility. The model informs analysis; a quiet numerical error is
  worse than a build failure.
- **A Rust skill requirement.** The repo has two contributors and nothing in its history shows Rust in
  use. Introducing it makes the compiled core maintainable by a smaller set of people — and unlike the
  C++, which at least mirrors upstream and can be checked against the R package, a Rust core cannot be
  reviewed by reference to anything.
- **Churn on a v0.1.0 package** whose publish path is not yet proven end to end: issue #9 remains open,
  and PRs #8 and #10 are both unmerged. Stacking a rewrite on top of unfinished release plumbing is
  poor sequencing.

## Decision triggers

**Port — revisit (b), then (a) — if any two of these become true:**

- Upstream `bw` is declared dormant or archived, or `ahl_dwc` has already diverged materially (for
  example a local model change is merged into `adult_weight.cpp`). At that point the upstream link is
  already gone and its loss stops being a cost.
- `child_weight` (issue #4) is scheduled. That adds a second model of comparable size; doing it in Rust
  makes the port cheaper per line and gives a natural greenfield first target.
- A second GCC/Clang or libstdc++/libc++ divergence lands and costs more than a day — that is,
  `bf87e07` turns out to be a pattern rather than an incident.
- Value-pinned Brownian becomes a hard requirement for a downstream analysis _and_ the pinned-C++-PRNG
  fix in (c2) proves inadequate.
- Someone on the team is fluent in Rust and will own the crate for at least a year. One enthusiast on a
  two-person repo is not this.
- The hardened suite exists and is demonstrably strong: a deliberate perturbation to
  `adult_weight.cpp` — say a 1% change to one constant — is caught by multiple tests.

**Do not port if any of these hold:**

- Upstream `bw` is active and the team expects to track its fixes.
- The regression suite is still four golden endpoints. Without a stronger net, a port is hope, not
  engineering.
- The motivation is cross-platform wheels. cibuildwheel gets that in 2–3 days.
- The motivation is "C++ is unpleasant". True, and not sufficient.
- Nobody has capacity for the 15–25-day tail _including_ the numerical-discrepancy chase, which is the
  part that always overruns.

## If we do it — ordered task list

Steps 1–4 are prerequisites and are worth doing under option (c) as well. Do not start step 5 until
step 4 is green.

1. **Harden the regression suite.** More goldens (both sexes, all four BMI buckets, `n_ind > 1`,
   `dt != 1.0`, non-default `pal`/`pcarb`/`pcarb_base`); full-trajectory `.npz` fixtures rather than
   endpoints; a committed `capture_goldens.py` recording platform and compiler. (3.5–5.5 days)
2. **Add property tests** for the reconstruction identity, the BMI identity, monotonicity under a
   sustained deficit, and shape invariants. (1–2 days)
3. **Decide and record the Brownian contract** — that Rust Brownian output will differ from C++ and
   will be value-pinned thereafter. Write it down before any code changes. (0.5 day)
4. **Scaffold the dual build**: a `crates/ahl_dwc_core` crate, PyO3 plus `rust-numpy`, maturin, building
   into `ahl_dwc._core_rs` alongside the existing `_core`. Add a Rust leg to
   `.github/workflows/tests.yml` with `cargo fmt --check` and `cargo clippy -D warnings` blocking.
   (2–3 days)
5. **Port `src/energy_build.cpp`** (123 lines) — all six deterministic modes plus the Brownian bridge —
   over `ndarray` and `rand`/`rand_distr`, with an explicitly threaded and exactly pinned RNG.
   (2–3 days)
6. **Build the differential harness**: randomised inputs, both extensions in one process, tight
   agreement asserted for the deterministic modes. Run it in CI. (1–2 days)
7. **Switch `energy_build` in `ahl_dwc/__init__.py` to the Rust path**, ship, and let it sit through at
   least one real analysis cycle before continuing. This is the honest stop-or-continue gate.
8. **Port `adult_weight`** in dependency order — parameters and initial conditions, the six derivative
   functions, `fatMass`/`R`/`BMIClassifier`, then `rk4` last — each function differentially tested
   against its C++ counterpart before moving on. Preserve the staggered lean-mass scheme
   (`adult_weight.cpp:532-537`), the `nsims` cap (`:453`) and the `floor(t/dt)` forcing lookup
   (`:580-589`) exactly, with a comment at each site explaining that the oddity is deliberate.
   (8–12 days)
9. **Delete `src/`, `CMakeLists.txt` and the scikit-build-core build system**; move the build backend to
   maturin; switch the publish workflow to `maturin-action` with a full wheel matrix; reduce the C++
   sections of `README.md` ("Implementation details", "How it works") to a historical note.
10. **Record the divergence.** Pin the exact upstream `bw` commit the Rust port was translated from, and
    add a documented process for reviewing future upstream changes by hand — because from that point
    on, that is the only way they arrive.
