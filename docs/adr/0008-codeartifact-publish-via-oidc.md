---
status: accepted
date: 2026-07-09
deciders: Solomon Yu (sqr00t)
---

# 0008. Publish to private AWS CodeArtifact via GitHub OIDC, and `unset UV_INDEX` locally

## Context

Consumers were installing straight from git (`uv add git+https://github.com/nestauk/ahl_dwc.git
--tag v0.1.0`), which compiles the extension on every install and offers no version resolution.
Nesta already runs a private CodeArtifact PyPI, so the package should be installable from an index
(issue #5).

Two constraints shaped the design:

1. **The repo is public.** The CodeArtifact endpoint is an internal AWS detail and must not appear in
   any tracked file — not in `pyproject.toml`, and not in `uv.lock`.
2. **No long-lived AWS credentials in GitHub.** Access keys stored as secrets are the failure mode
   this design exists to avoid.

## Decision

**Publishing.** A workflow (`.github/workflows/publish-codeartifact.yml`) fires on
`release: [published]`, checks out the released tag, runs `uv build`, assumes an AWS role via GitHub
OIDC, mints a short-lived CodeArtifact token, and runs `uv publish`. No credential is stored.

| Step | Detail |
|---|---|
| Trigger | `release: types: [published]`, plus `workflow_dispatch` with an optional `tag` input added in `4436e23` "for re-runs / testing" |
| Guard | `if: ${{ !github.event.release.prerelease }}` (line 34) — `vX.Y.Z.dev0` versions are never published |
| Checkout | `ref: ${{ github.event.inputs.tag || github.event.release.tag_name }}` |
| Build | `uv build` on `ubuntu-latest` — one linux/x86_64 wheel plus an sdist |
| Auth | `permissions: id-token: write`; `aws-actions/configure-aws-credentials@v4` with `role-to-assume: secrets.AWS_ROLE_ARN` — the comment says "no long-lived keys" |
| Token | `aws codeartifact get-authorization-token`, `::add-mask::`ed into `$GITHUB_OUTPUT` |
| Publish | `uv publish` with `UV_PUBLISH_USERNAME: aws` — the comment notes the username **must** be `aws`, not `__token__` — and `UV_PUBLISH_URL` assembled from secrets and variables (trailing slash required) |

Configuration lives entirely in GitHub settings, never in the repo: secrets `AWS_ROLE_ARN`,
`AWS_CA_DOMAIN`, `AWS_CA_REPO`, `AWS_ACCOUNT_ID`; variable `AWS_REGION`. The AWS-side trust policy
(GitHub OIDC provider, conditioned on `repo:nestauk/ahl_dwc:*`) and permissions
(`codeartifact:GetAuthorizationToken`, `PublishPackageVersion`, `PutPackageMetadata`,
`sts:GetServiceBearerToken`) are **not in the repo** — inferred from what the workflow calls.

Versions are bumped by hand in `pyproject.toml:12` before tagging. There is no bump tool, no
`setuptools-scm`, no dynamic version.

**Local lock hygiene.** `.envrc` gains `unset UV_INDEX` (`2f46f9d`), so a shell configured for
CodeArtifact does not bake the private index URL into the committed `uv.lock`:

```bash
# Keep local uv operations on public PyPI so the private-index URL is never
# written into uv.lock. Temporary until the private-index workflow is finalised.
unset UV_INDEX
```

This is self-declared temporary and is therefore a live open thread, not a settled arrangement. It
was made twice, independently, on two branches (`2f46f9d` on `fix/gcc-cpp-compat` and `638e481` on
`cpp-test-harness`).

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Long-lived AWS access keys as GitHub secrets | Explicitly rejected in the workflow comment: "no long-lived keys". OIDC gives short-lived STS credentials scoped to this repository. |
| Put the CodeArtifact index URL in `pyproject.toml` or `uv.lock` | Rejected because the repo is public — stated in issue #9's acceptance criteria. This is also the whole reason for `unset UV_INDEX`. |
| Keep git-tag installs as the only route | Recompiles on every install, gives no dependency resolution, and ties consumers to GitHub auth. Still documented in `README.md` as the fallback, because it works on every platform. |
| **cibuildwheel** for multi-platform wheels | Named as the remedy in the workflow's own header comment, and not implemented. There is no `[tool.cibuildwheel]` section. |
| A three-leg publish matrix (macOS blocking + wheel and sdist, two Linux legs non-blocking) | **Fully implemented and unmerged** — `0ac4dff` on `ci/matrix-build`, PR #8, issue #9. Held back because its Linux legs cannot compile until ADR 0007's fix lands. Issue #9 records the macOS leg as confirmed green ("wheel uploaded; only a 409 on the pre-existing 0.1.0 sdist"). |
| Build-provenance attestation | Written and **commented out** (`publish-codeartifact.yml:53-57`, `actions/attest-build-provenance@v1`), while `attestations: write` is still granted. Deliberately deferred. |
| Fix `UV_INDEX` pollution structurally (an explicit `[tool.uv.index]`, or CI-side lock verification) | Not done. `.envrc` is the stopgap; it only works if direnv is installed **and** `direnv allow` has been run in the checkout. |

## Consequences

Positive:

- No AWS credential exists in GitHub to leak or rotate; the token is minted immediately before use.
- Nothing in the public repo names the internal endpoint (verified: `uv.lock` contains 261
  `pypi.org/simple` sources and zero CodeArtifact URLs).
- Pre-release Releases are skipped rather than published, so `dev` versions cannot reach the index by
  accident through the release path.
- `workflow_dispatch` with `tag` makes a failed publish re-runnable without cutting a new release.

Negative:

- **One platform wheel.** `uv build` on a single Linux runner produces a linux/x86_64 wheel and an
  sdist. macOS (Intel and Apple silicon), Linux arm64, Windows, and any mismatched ABI fall back to
  the sdist — meaning those consumers compile the C++ locally and need a compiler and CMake ≥ 3.15.
  Install is slow and fails outright on a machine without build tools. The workflow says so itself in
  its header.
- **And that one wheel is currently unproducible.** Per ADR 0007, `main` does not compile under GCC,
  so the only artefact that appears ever to have been published is the macOS wheel from the PR #8
  test run.
- **The pre-release guard is inert on manual dispatch.** `github.event.release` does not exist on
  `workflow_dispatch`, so `github.event.release.prerelease` is empty and the condition is true.
  Dispatching with `tag: v0.2.0rc1` **will** build and publish it, and CodeArtifact will not let you
  overwrite it afterwards.
- **Nothing cross-checks the tag against `pyproject.toml`.** The version published is whatever the
  file says at that tag; a mismatch silently ships the wrong number.
- **Publishing is not idempotent.** A re-run against an existing version fails with a 409. Issue #9
  leaves "make publish idempotent, e.g. `uv publish --check-url`" as its one unticked box.
- **The repo's own install instruction does not use the index it publishes to** — `README.md`
  documents the git-tag route. Whether `v0.1.0` was ever successfully published is unverified: the
  tag (`c8910f9`, 2025-12-22) predates the publish workflow (`eef6b39`, 2026-07-09) by seven months,
  though issue #9's mention of a 409 on "the pre-existing 0.1.0 sdist" implies something is there.
- **No provenance attestation** is produced, despite the permission being granted.
- **`unset UV_INDEX` is a convention, not a control.** It depends on direnv being installed and
  allowed; nothing in CI verifies the lock is clean. The recovery when it fails is manual:
  `env -u UV_INDEX uv lock`, then confirm no CodeArtifact URL remains.

## Evidence

- `eef6b39` + `4436e23` (2026-07-09 10:53–10:56), merged as PR #6 (`e63a2ce`, 11:10), closing
  issue #5. `e63a2ce` is the last commit on `main`.
- `.github/workflows/publish-codeartifact.yml:9-12` (single-platform note, cibuildwheel remedy),
  `:13-23` (triggers), `:25-28` (permissions), `:34` (pre-release guard), `:51` (`uv build`),
  `:53-57` (commented-out attestation), `:63` (role), `:71-75` (token), `:83-87` (publish).
- `2f46f9d` (2026-07-23 10:54) and `638e481` (2026-07-22, `cpp-test-harness`) — `unset UV_INDEX`.
- `.envrc:5-7`.
- Issues #5 (closed) and #9 (open); PR #8 (open) and commit `0ac4dff`.
- `README.md` install section; `pyproject.toml:12` (hand-bumped version).
