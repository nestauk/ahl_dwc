# Runbook: sync C++ from upstream `INSP-RH/bw`

Goal: pull a change from the upstream R package's C++ into `src/` without breaking the shim,
and prove the numbers did not move by accident.

The scientific core of this repository is not ours. `src/adult_weight.cpp`,
`src/adult_weight.h` and `src/energy_build.cpp` are ported from
[`INSP-RH/bw`](https://github.com/INSP-RH/bw); `src/shim.hpp` and `src/bindings.cpp` are
entirely ours and exist to stand in for Rcpp. The whole sync procedure is about keeping that
boundary clean.

## 0. File policy

| File                   | Origin   | Policy                                                                                                                                 |
| ---------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `src/adult_weight.cpp` | upstream | Track upstream. **Code must not diverge.** Comment drift is tolerated                                                                  |
| `src/energy_build.cpp` | upstream | Track upstream code. It carries one _required_ local edit: `#include "shim.hpp"` at line 38                                            |
| `src/adult_weight.h`   | upstream | Track upstream structure. One required local edit: `#include "shim.hpp"` at line 32, replacing upstream's `math.h` / `Rcpp.h` includes |
| `src/shim.hpp`         | ours     | Never taken from upstream. Extend only as new upstream code demands                                                                    |
| `src/bindings.cpp`     | ours     | Never taken from upstream. Edit when the exposed surface changes                                                                       |
| `CMakeLists.txt`       | ours     | Add new upstream `.cpp` files to `pybind11_add_module` here                                                                            |

The README's "Implementation details" table describes `adult_weight.cpp` as "Upstream `bw`
code, unchanged" and `energy_build.cpp` as the same "with one added line". That is true of the
**code**, not of the files. Both were brought back toward upstream in commit `75b1c37` by
re-adding upstream's MIT header comments, and `energy_build.cpp:38` swaps the include. Read
"unchanged" as "unchanged in code, with the include swap and comment drift".

Not ported, deliberately: upstream's `child_weight` model. See issue #4 — it becomes relevant
only if all analysis migrates to Python.

## 1. Get upstream

Add the remote once, then fetch:

```bash
git remote add bw https://github.com/INSP-RH/bw.git 2>/dev/null || true
git fetch bw
git log --oneline -20 bw/master -- src/
```

The upstream default branch name and the exact upstream paths under `src/` are
**unverified from this repository** — confirm with `git ls-tree bw/master src/` and adjust
the commands below if they differ.

Record the upstream commit you are syncing from. You will need it for the PR description and
any ADR:

```bash
git rev-parse --short bw/master
```

## 2. Diff our port against upstream

Compare each ported file individually. `-w` ignores whitespace-only churn; drop it when you
want to see everything.

```bash
git diff -w bw/master:src/adult_weight.cpp  -- src/adult_weight.cpp
git diff -w bw/master:src/adult_weight.h    -- src/adult_weight.h
git diff -w bw/master:src/energy_build.cpp  -- src/energy_build.cpp
```

Expected diff, and nothing else:

- In `adult_weight.h`: upstream's `#include <math.h>` / `#include <Rcpp.h>` replaced by
  `#include "shim.hpp"`.
- In `energy_build.cpp`: `#include "shim.hpp"` added (`math.h` is retained alongside it).
- Comment and header-block differences.

**Any other hunk is unexplained divergence.** Stop and account for it before continuing —
either it is a local fix that should have been recorded (record it now), or the previous sync
was incomplete.

To see what upstream changed since the last sync, if you know the previous upstream commit:

```bash
git diff <previous-upstream-sha> bw/master -- src/
```

## 3. Bring the change across

Prefer applying upstream's diff to our files over copying files wholesale — copying loses the
include swap and the header comments every time.

```bash
git diff <previous-upstream-sha> bw/master -- src/adult_weight.cpp > /tmp/up.patch
git apply --3way /tmp/up.patch
```

If you do copy a file wholesale, immediately re-apply the include swap (§4) and re-diff.

If upstream added a **new** source file you need, add it to `CMakeLists.txt`:

```cmake
pybind11_add_module(_core
    src/bindings.cpp
    src/adult_weight.cpp
    src/energy_build.cpp
    src/<new_file>.cpp
)
```

## 4. Re-apply the shim include swap

Upstream compiles against Rcpp. We do not. Every ported translation unit must reach the shim
instead.

In `src/adult_weight.h`, upstream's include block becomes:

```cpp
#include "shim.hpp"
```

In `src/energy_build.cpp`:

```cpp
#include "shim.hpp"
#include <math.h>
```

`src/adult_weight.cpp` needs nothing — it includes `adult_weight.h`, which pulls the shim in.

Verify no Rcpp reference survives:

```bash
grep -rn 'Rcpp\|RcppArmadillo\|Rcout' src/ || echo "clean"
```

(`shim.hpp` defines `Rcout` as `std::cout`; a hit there is expected. A hit in a ported file
that is not commented out is not.)

## 5. Extend the shim if upstream used something new

If the new upstream code calls an Rcpp construct the shim does not implement, the compile
will fail with an undefined name. Add it to `src/shim.hpp`, matching the existing patterns:
`NumericVector` / `NumericMatrix` / `StringVector` wrappers, the `DEF_OP` elementwise
operator macro, the `Slice` sentinel `_`, and `List::create` / `Named`.

Two rules when doing so, both learned the hard way:

- **Do not redeclare constructors that `std::vector` already provides.** See the comment at
  `src/shim.hpp:45-56` and commit `bf87e07`: redeclaring `(n)` and `(n, v)` alongside
  `using std::vector<double>::vector;` made `NumericVector(int, 0.0)` ambiguous under
  GCC/libstdc++ while compiling fine under Clang/libc++.
- **Anything touching randomness is not portable.** `std::normal_distribution` is
  implementation-defined; do not pin its values in tests.

## 6. Build and re-verify the golden values

```bash
uv sync --reinstall-package ahl-dwc
uv run pytest -q
```

`--reinstall-package` is not optional here — a stale `_core` will happily report green on
code you have not compiled. See `docs/runbooks/local-development.md` §5.

Then run the full matrix, because a shim change is exactly the kind that compiles on one
toolchain and not another:

```bash
uvx --with tox-uv tox run
```

### If the regression tests fail

Work through the decision procedure in `docs/runbooks/ci-triage.md` §6 first. The short
version, in this context:

| Observation                                                                     | Meaning                                                                  |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Goldens move by grams, on one platform only                                     | Platform libm/FMA drift. Do not touch the goldens                        |
| Goldens move by 0.1 kg or more, on every platform                               | Upstream changed the model. This is a real, reportable change            |
| Analytic tests (`energy_build` Linear, the no-intake-change baseline) also fail | Something broader broke — the shim, the build flags, or the include swap |

If upstream genuinely changed the model, re-capture the goldens rather than loosening the
tolerance:

```bash
uv run python - <<'PY'
import numpy as np
from ahl_dwc import adult_weight
DEFICIT = {"ei_change": np.full(365, -250.0), "na_change": np.full(365, -20.0)}
cases = {
    "female_deficit": {"bw": 80, "ht": 1.8, "age": 40, "sex": "female", **DEFICIT},
    "male_deficit": {"bw": 90, "ht": 1.85, "age": 35, "sex": "male", **DEFICIT},
    "ei_variant": {"bw": 80, "ht": 1.8, "age": 40, "sex": "female", "days": 365, "ei": 2500},
    "ei_fat_variant": {"bw": 80, "ht": 1.8, "age": 40, "sex": "female", "days": 365, "ei": 2500, "fat": 24},
}
for name, kw in cases.items():
    print(f"{name}: {np.asarray(adult_weight(**kw)['Body_Weight'])[0][-1]:.6f}")
PY
```

Paste the new values into `GOLDEN` at `tests/regression/test_adult_weight.py:23-32` and — in
the PR description — state the OS, architecture, compiler version and Python version that
produced them. The existing goldens carry no such record; do not repeat that.

## 7. What to record

Every sync PR should state:

1. The upstream commit synced from and the previous one.
2. Which files changed and whether the change was code or comments.
3. Whether the goldens moved, by how much, and on which platform they were re-captured.
4. Any shim additions.

### When it warrants an ADR

Write an architecture decision record (in `docs/adr/`, alongside the existing records) when
the sync involves a decision rather than a transcription:

| Situation                                                           | ADR?                                                                            |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Upstream fixed a typo or a comment                                  | No                                                                              |
| Upstream changed a model constant or an equation, goldens move      | **Yes** — the numbers our consumers depend on changed                           |
| We deliberately decline to take an upstream change                  | **Yes** — a divergence nobody records will be silently "fixed" by the next sync |
| We port a new upstream model (for example `child_weight`, issue #4) | **Yes**                                                                         |
| The shim gains a new Rcpp construct                                 | Only if it changes the shim's design, not for a routine addition                |
| Upstream drops Rcpp or restructures its build                       | **Yes** — this is the assumption the whole port rests on                        |
| A sync forces a compiler, C++ standard or dependency change         | **Yes**                                                                         |

Anything less than that belongs in the commit message and the PR description.
