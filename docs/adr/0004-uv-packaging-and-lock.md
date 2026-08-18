---
status: accepted
date: 2025-11-20
deciders: Harry Wilde (HarrisonWilde); tox-uv addition by Solomon Yu (sqr00t), 2026-07-23
---

# 0004. uv as the packaging, environment and lock tool

## Context

The project needs one command that creates an environment, resolves and pins runtime and dev
dependencies, **and** compiles the C++ extension into that environment. It also has to work
identically on a developer laptop, in CI across five Python versions, and in the release job.

uv is the Nesta data-science default for non-conda Python projects, and it predates the C++ work
here: `uv.lock` and `[tool.uv] package = true` arrived with the cookiecutter skeleton (`0194747`)
and survived the rewrite that deleted almost everything else (`76246e0`).

## Decision

We use **uv** as the single entry point, with a committed `uv.lock`, and declare the project itself
a package so that `uv sync` builds and installs the extension:

```toml
[tool.uv]
package = true
```

Consequences of that one flag: `uv sync` runs the scikit-build-core backend (ADR 0003), compiles
`_core`, and installs `ahl_dwc` editable into `.venv`. There is no separate build step in the
developer loop, and no Makefile.

Dev tooling lives in `[dependency-groups] dev` (`pyproject.toml:23-32`; the `dev` list opens at `:24`), not in an extra — matplotlib
was demoted there from a runtime dependency in `75b1c37` because only
`examples/reproduce_bw_vignette.py` needs it.

Later (`dd4e80f`, 2026-07-23) the Python-version dimension was added as **tox with the
`uv-venv-lock-runner`**, keeping uv as the environment builder underneath:

```toml
[tool.tox]
requires = ["tox>=4.21", "tox-uv>=1.13"]
env_list = ["py310", "py311", "py312", "py313", "py314"]

[tool.tox.env_run_base]
runner = "uv-venv-lock-runner"
dependency_groups = ["dev"]
commands = [["pytest", "-q"]]
```

Run it exactly as CI does with `uvx --with tox-uv tox run`, or a single leg with
`uvx --with tox-uv tox run -e py312`.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| conda + `environment.yaml` + `make install` (the Nesta ds-cookiecutter default) | Present at `0194747` and deleted 54 minutes later with the rest of the scaffolding (`76246e0`). For a package that must produce wheels and publish to a PyPI-protocol index, a PEP 517 + lockfile workflow is the closer fit. Note `.envrc` survives but activates nothing — it is not a conda `.envrc`. |
| pip + `requirements.txt` | No lock semantics, no dependency groups, no build integration; nothing in the history suggests it was considered. |
| Poetry (used elsewhere in the Nesta estate) | Not evidenced. Poetry's build backend would have had to be swapped out for scikit-build-core anyway. |
| Putting Python versions in the GitHub matrix instead of tox | Explicitly rejected in ADR 0007 — the version dimension lives in `pyproject.toml` so it is reproducible locally. |

## Consequences

Positive:

- One command (`uv sync`) gives a working, compiled, test-ready checkout.
- `uv.lock` pins the full runtime and dev graph — 127 packages, lockfile `version = 1`,
  `revision = 3` — so CI and laptops resolve identically.
- Every `source` in the lock is `registry = "https://pypi.org/simple"` (verified: 261 occurrences, no
  CodeArtifact URL). That is the state ADR 0008's `unset UV_INDEX` exists to preserve.
- tox-uv reuses the same lock across all five Python versions, so the matrix tests the pinned graph
  rather than a fresh resolution per leg.

Negative:

- **`uv.lock` does not cover the build system.** Neither `scikit-build-core` nor `pybind11` appears
  in it (verified: zero matches), so the compiler-facing half of the build is unpinned. See ADR 0003.
- **`requires-python = ">=3.8"` propagates into the lock**, giving four `resolution-markers`
  including `python_full_version < '3.9'` and several pinned versions of NumPy, polars and pytest —
  extra lock churn for Python versions that are never tested and on which the package cannot even be
  imported (`ahl_dwc/__init__.py:10` uses PEP 604 unions in runtime-evaluated signatures with no
  `from __future__ import annotations`, so 3.8/3.9 raise `TypeError` on import).
- The lock is easy to pollute: a shell with `UV_INDEX` set writes a private CodeArtifact URL into it
  from a public repo. Mitigated, temporarily, by `.envrc` (ADR 0008).
- No `Makefile` and no documented rebuild target, so the "stale `_core` after a C++ edit" case has no
  blessed incantation; `uv sync --reinstall-package ahl-dwc` or a fresh tox leg
  (`uvx --with tox-uv tox run -e py312 -r`) are the working ones (inferred — the repo documents
  neither).

## Evidence

- `0194747` (2025-11-20) introduces `uv.lock` and `[tool.uv]`; `76246e0` keeps them while deleting
  the rest of the cookiecutter.
- `pyproject.toml:34-35` (`package = true`), `:23-32` (dev group), `:37-45` (tox).
- `dd4e80f` (2026-07-23) "build: add [tool.tox] py3.10-3.14 test envs (tox-uv)".
- `75b1c37` demotes matplotlib to the dev group.
- `uv.lock:1-3` — `version = 1`, `revision = 3`, `requires-python = ">=3.8"`.
- `.github/workflows/tests.yml:31-37` — `uv python install 3.10 … 3.14`, then
  `uvx --with tox-uv tox run` with `UV_PYTHON_PREFERENCE: only-managed`.
