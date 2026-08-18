---
status: proposed
date: 2026-08-18
deciders: not yet decided
---

# 0009. Evaluate a Rust reimplementation with PyO3 bindings

> Date note: there is no git evidence for this decision. 2026-08-18 is the date this ADR was first
> written, not the date of a decision.

## Context

Most of the recurring costs recorded in ADRs 0002, 0003, 0006 and 0007 trace to the same root: a
hand-written C++ shim over unowned upstream sources, built with no pinned standard and no pinned
build dependencies.

- The shim has no bounds checking and returns `NaN` (or reads out of bounds) where it should raise
  (ADR 0002).
- A toolchain-dependent overload resolution broke every Linux build once already (ADR 0007).
- The upstream sources cannot be reformatted or warning-cleaned without abandoning ADR 0002, so
  `clang-format` and `cppcheck` are permanently advisory.
- Distribution requires a C++ toolchain on every consumer platform that lacks a wheel (ADR 0008).

A Rust core with PyO3 bindings and `maturin` would address memory safety, a pinned toolchain, a
lockfile that covers the build, and straightforward cross-platform wheels — at the cost of
reimplementing numerics we currently inherit for free, and losing the "attributable to the shim, not
the model" property that ADR 0002 buys.

## Decision

**Not yet taken.** This ADR exists to name the question and hold a number for the answer.

The question to answer: *should the numerical core be reimplemented in Rust with PyO3 bindings, or
should we continue wrapping upstream `bw`'s C++?*

The substance — scope, equivalence-testing strategy, effort estimate, and the case for and against —
is deliberately not duplicated here. See **[`docs/rust-port.md`](../rust-port.md)**.

This ADR should be updated to `accepted` or `rejected` once that evaluation concludes, with the
decision and its consequences filled in.

## Alternatives considered

See `docs/rust-port.md`. At minimum the evaluation must weigh: status quo (ADR 0001), a Rust
reimplementation, and the cheaper partial options — hardening the existing Python and shim layers
with real validation, and adopting `cibuildwheel` (ADR 0008) to remove the distribution pain without
touching the numerics.

## Consequences

Unknown until the decision is taken. Note that a Rust reimplementation would supersede ADRs 0001,
0002 and 0003, and would require re-capturing every golden value in ADR 0006 against a new
implementation — which is precisely the equivalence problem ADR 0001 was written to avoid.

## Evidence

- `docs/rust-port.md` — the evaluation.
- ADRs 0001, 0002, 0003, 0006, 0007, 0008 for the costs this proposal responds to.
- No commit, issue or PR in this repository proposes this work as of `2f46f9d` (2026-07-23).
