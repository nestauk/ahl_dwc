# Runbook: CI triage

Goal: a check is red on a pull request. Work out which layer broke and fix it.

Three workflows run on every pull request:

| Workflow | Job | Blocking |
|---|---|---|
| `Tests` (`.github/workflows/tests.yml`) | `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-latest` | Yes |
| `Format` (`.github/workflows/format.yml`) | `python` (ruff) | Yes |
| `Format` | `cpp` (clang-format, cppcheck) | **No** — `continue-on-error: true` |
| `Publish to CodeArtifact PyPI` | `publish` | Does not run on pull requests |

## 0. Read the failure

```bash
gh pr checks
gh run list --branch "$(git branch --show-current)" --limit 5
gh run view <run-id> --log-failed
```

`fail-fast: false` on the test matrix means all three OS legs always run — the pattern of
which legs failed is the primary diagnostic signal.

| Pattern | Read it as |
|---|---|
| All three legs fail | Python-level bug, or a genuine model/test change |
| Both Linux legs fail, macOS green | GCC/libstdc++ vs Clang/libc++ — go to §2 |
| One Linux leg fails (x86_64 xor arm64) | Architecture-specific: SIMD/FMA or an arch-conditional compile path |
| macOS only | Clang-specific, or a libm difference in the golden values |
| One Python version inside a leg | Go to §3 |

## 1. Tests workflow — anatomy

Each leg runs `uvx --with tox-uv tox run` with `UV_PYTHON_PREFERENCE: only-managed`, after
`uv python install 3.10 3.11 3.12 3.13 3.14`. The Python dimension lives in `[tool.tox]`
(`pyproject.toml:37-45`), not in the GitHub matrix. So 3 OS jobs cover 15 environments, and
the log for one job contains five sequential tox environments — scroll to find which
`py3xx` failed, and whether it failed at build time or at test time.

Reproduce a single environment locally:

```bash
uvx --with tox-uv tox run -e py312 -r
```

`-r` recreates the environment, which is what you want when the extension may be stale.

## 2. Linux legs fail, macOS passes — the GCC/libstdc++ case

This is the workflow's stated reason for existing (`tests.yml:5`: "The Linux legs guard the
GCC/libstdc++ build"), and it has fired for real.

**Precedent.** Commit `bf87e07`, "fix: remove duplicate NumericVector ctors for GCC compat".
`class NumericVector` in `src/shim.hpp` declared `using std::vector<double>::vector;` *and*
redeclared `NumericVector(size_t)` and `NumericVector(size_t, double)`. A call like
`NumericVector(cols, 0.0)` with an `int` `cols` was then ambiguous between the inherited fill
constructor and the redeclared one — both require the same `int -> size_t` conversion. GCC
rejects this per the standard; Clang resolves it. Error text was:

```
src/shim.hpp:186:43: error: call of overloaded 'NumericVector(int&, double)' is ambiguous
```

The fix was to delete the redeclarations and rely on the inherited constructors only; the
reasoning is recorded in-source at `src/shim.hpp:45-56`.

**Triage steps.**

1. Confirm it is a *compile* error, not a test failure. Look for `error:` from `g++` in the
   CMake build output, before any pytest line.
2. Reproduce on Linux — do not iterate through CI:

   ```bash
   docker run --rm -it -v "$PWD":/w -w /w ubuntu:24.04 bash -lc \
     'apt-get update -qq && apt-get install -y -qq build-essential cmake curl >/dev/null && \
      curl -LsSf https://astral.sh/uv/install.sh | sh && ~/.local/bin/uv sync && ~/.local/bin/uv run pytest -q'
   ```

   A faster syntax-only loop, if you have a GCC to hand:

   ```bash
   g++ -std=c++17 -fsyntax-only -Wall -Wextra -Isrc src/adult_weight.cpp
   ```

**Rejected fixes** (both were considered and ruled out on the original issue):

| Attempt | Why not |
|---|---|
| `-fpermissive` | This is a hard error, not a warning; the flag does not apply |
| Casting the argument to `size_t` | The ambiguity is by-value vs const-ref — both are already exact matches |
| Dropping the Linux leg | The leg exists specifically to catch this class of bug |

**Correct fix pattern:** prefer inherited constructors; do not redeclare overloads libstdc++
also provides; avoid brace-init where a fill-vs-initializer-list ambiguity could arise.

Related standing risk: no C++ standard is pinned (`CMakeLists.txt` sets no
`CMAKE_CXX_STANDARD`), so each toolchain applies its own default. If a failure looks like a
language-version difference rather than an overload problem, that is the reason.

## 3. One Python version fails, the others pass

Because tox drives the Python dimension, the failing environment shows up as a `py3xx`
section inside an otherwise-normal job.

| Cause | Signal | Fix |
|---|---|---|
| No wheel / build failure for a new interpreter (3.14 is the usual suspect) | The failure is in a dependency install or the extension build, not in pytest | Wait for upstream wheels, or pin the dependency; do not silently drop the env from `env_list` without saying why |
| Syntax or typing feature unavailable on 3.10 | `SyntaxError` / `TypeError` on import | Lower the construct, or raise the floor deliberately |
| Deprecation turned error in a newer numpy/polars | `DeprecationWarning`-shaped `TypeError` in the failing env only | Fix the call site |

Reproduce exactly:

```bash
uv python install 3.14
uvx --with tox-uv tox run -e py314 -r
```

Note the declared floor is wrong: `requires-python = ">=3.8"` but the package cannot import
below 3.10 (PEP 604 annotations evaluated at runtime in `ahl_dwc/__init__.py`). CI never
catches this because it only installs 3.10-3.14. A failure report from a 3.9 user is not a
CI bug.

## 4. `Format / python` (ruff) is red — blocking

```bash
uvx ruff@0.14.10 check .
uvx ruff@0.14.10 format --check .
uvx ruff@0.14.10 format .          # apply formatting
uvx ruff@0.14.10 check --fix .     # apply safe lint fixes
```

Pin `0.14.10` exactly. It is stated in `.pre-commit-config.yaml` and repeated in
`format.yml:22` with a comment saying so, and a different local ruff will disagree with CI.

Config lives at `pyproject.toml:50-78`: line length 120; `select = ["ANN","B","C","E","F","I","N","W"]`;
isort first-party `ahl_dwc`; `tests/**` exempt from `ANN`/`D100`/`D103`; `__init__.py` exempt
from `F401`/`E402`/`D104`. Note `D` is configured (google convention) but not selected, so
docstring rules are not enforced — do not "fix" a docstring complaint that ruff never made.

Best avoided entirely: run `prek run --files <paths>` before committing. The
`pre-commit-update` hook auto-bumps hook revisions, so if `.pre-commit-config.yaml` moves off
`0.14.10` the pin in `format.yml` must be updated by hand in the same PR.

## 5. `Format / cpp` — non-blocking today

The job runs:

```bash
clang-format --dry-run --Werror --style=Google src/*.cpp src/*.hpp src/*.h
cppcheck --enable=warning,portability --suppress=missingIncludeSystem --error-exitcode=1 src/
```

under `continue-on-error: true` (`format.yml:30`). The header explains why: the ported `bw`
sources are not Google-formatted, and the job is advisory "until a dedicated clang-format
pass lands".

Consequences to hold in mind:

- The check **reports green even when the commands fail**. You have to open the log.
- It therefore also masks a genuine problem in newly written C++. If you touched
  `src/shim.hpp` or `src/bindings.cpp`, open the log and read the findings for your files
  specifically; ignore the noise on `adult_weight.cpp` / `energy_build.cpp`.
- Known pre-existing warnings, reproducible with `c++ -std=c++17 -Wall -Wextra -fsyntax-only`:
  `-Wreorder-ctor` at `src/shim.hpp:145` and `:221` (benign — both constructors initialise
  `data` from the parameters, not the members), and `-Wsign-compare` at
  `src/adult_weight.cpp:422` in the BMI classifier loop.
- The step globs three patterns. If a category ever empties (for example the last `.hpp` is
  removed), the glob goes unexpanded and clang-format errors on a literal path. Inferred, not
  observed.

To make it blocking: land a repo-wide clang-format pass plus a checked-in `.clang-format`,
then remove `continue-on-error`. That is a deliberate decision, not a drive-by change.

## 6. A numerical regression test fails

Failing tests are in `tests/regression/`. The decision you need to make is: **real model
change, or platform floating-point drift?**

The tolerances encode the intended answer:

| Test | Tolerance | Rationale |
|---|---|---|
| Golden final weights (`test_adult_weight.py:23-32`) | `PHYS_RTOL = 1e-4` | "Loose enough for cross-platform libm/FMA differences, tight enough that a real model regression (order 0.1 kg+) fails" |
| No-intake-change baseline | `atol=1e-6` against 80.0 | Analytically exact |
| `energy_build` Linear | `rtol=1e-9` | Analytic |
| Brownian | none — seed reproducibility and seed variance only | `std::normal_distribution` is implementation-defined and not portable across standard libraries |

### Decision procedure

1. **Get the magnitude.** Read the assertion output: what is the observed value against the
   golden (73.178765, 83.194082, 85.140406, 85.154781 kg for the four scenarios)?

   - Deviation at or beyond ~0.1 kg (relative ~1e-3): **real change**. `PHYS_RTOL` was
     chosen so that model regressions fail. Go to 3.
   - Deviation just over `1e-4` relative (order grams): ambiguous. Go to 2.

2. **Check the failure's platform pattern.**

   - Fails on every OS and every Python: not floating-point drift. Real change.
   - Fails on exactly one OS or one architecture, with the others green and the deviation
     tiny: consistent with libm/FMA drift. Nothing in the build pins an optimisation level
     or an FP model, so this is expected variation, not a bug in your diff.

3. **Check whether your diff can explain it.**

   ```bash
   git diff origin/main... -- src/ ahl_dwc/
   ```

   If `src/` is untouched and `ahl_dwc/__init__.py` is untouched, a numerical change is
   surprising — suspect a dependency (numpy) or a toolchain change in the runner image.

4. **Bisect the layer.** The `energy_build` Linear test is analytic; if it also fails, the
   problem is broad (compiler flags, standard library) rather than in the ODE integration.
   If only `adult_weight` goldens move, look at `src/adult_weight.cpp` and the shim's
   elementwise `exp`/`log`/`pow`.

5. **Act.**

   | Conclusion | Action |
   |---|---|
   | Real model change, intended | Re-capture the goldens, and say in the PR which platform and toolchain produced them. The current goldens' provenance is undocumented — do not repeat that |
   | Real model change, unintended | Fix the code. Do not widen `PHYS_RTOL` to make it pass |
   | Platform drift, single leg, grams | Do **not** re-capture. Document the observation. Widening the tolerance blunts the test's stated purpose, so treat it as a decision to record, not a quick fix |
   | Brownian values differ across platforms | Expected and already documented (`test_energy_build.py:1-7`). Never pin Brownian values |

Determinism is easy to confirm — `adult_weight` uses no RNG at all
(`test_adult_weight.py:56-59` asserts two identical calls return identical arrays). If a
result is non-deterministic *within* a process, that is a genuine bug, not drift.
