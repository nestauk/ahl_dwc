# Runbook: release and publish to CodeArtifact

Goal: cut a version of `ahl_dwc` and get it into the private AWS CodeArtifact PyPI
repository via `.github/workflows/publish-codeartifact.yml`.

The version is bumped **by hand**. There is no bump tool, no `setuptools-scm`, no dynamic
version — `version = "0.1.0"` at `pyproject.toml:12` is exactly what ships.

## 0. Know the limits before you start

- **One wheel only.** The workflow runs `uv build` on `ubuntu-latest`, producing an sdist
  plus a single linux/x86_64 CPython wheel. macOS, Linux arm64 and Windows consumers fall
  back to the sdist and compile locally. The remedy named in the workflow header is
  cibuildwheel; there is no `[tool.cibuildwheel]` section today.
- **You cannot overwrite a published version.** Plan the number before you tag.
- **The tag string is not the version.** Nothing cross-checks the tag against
  `pyproject.toml`. A mismatch silently ships the wrong number.

## 1. Pre-release checklist

Run each, in order, on the branch you intend to merge.

```bash
# 1a. Full matrix locally (CI is authoritative, this is the fast filter)
uvx --with tox-uv tox run

# 1b. Lint, exactly as CI pins it
uvx ruff@0.14.10 check . && uvx ruff@0.14.10 format --check .

# 1c. Lock is current and clean of the private index
uv lock --check
grep -c codeartifact uv.lock      # expect: 0
```

Then confirm on GitHub that all three `Tests` legs (`ubuntu-latest`, `ubuntu-24.04-arm`,
`macos-latest`) and the blocking `Format / python` job are green on the merge commit. The
`Format / cpp` job is `continue-on-error: true` and reports green regardless — open its log
if you care about the findings.

Bump the version:

```bash
# edit pyproject.toml:12 -> version = "0.2.0"
grep '^version' pyproject.toml
```

Commit on a branch (`no-commit-to-branch` blocks direct commits to `main`) and merge.

## 2. Tag

Tags follow `vX.Y.Z` — that is the convention in the workflow's own `workflow_dispatch`
example and in the README install line (`--tag v0.1.0`).

```bash
git checkout main && git pull
git show HEAD:pyproject.toml | grep '^version'   # must match the tag you are about to cut
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

## 3. Create the GitHub Release

Pushing the tag does nothing on its own. The trigger is `release: types: [published]`.

```bash
gh release create v0.2.0 --title "v0.2.0" --notes "…"
```

Do **not** tick "This is a pre-release" if you want it published — see step 6.

## 4. What the workflow does

| Step | Detail |
|---|---|
| 1 | `actions/checkout@v4` at `github.event.inputs.tag \|\| github.event.release.tag_name` |
| 2 | `astral-sh/setup-uv@v6`, cache enabled |
| 3 | `uv build` — compiles the extension, emits sdist + one linux/x86_64 wheel into `dist/` |
| 4 | Build-provenance attestation — **commented out**, though `attestations: write` is still granted |
| 5 | `aws-actions/configure-aws-credentials@v4` assumes `secrets.AWS_ROLE_ARN` via GitHub OIDC (`id-token: write`); no long-lived keys |
| 6 | `aws codeartifact get-authorization-token`, masked with `::add-mask::` |
| 7 | `uv publish` with `UV_PUBLISH_USERNAME: aws` and a `UV_PUBLISH_URL` assembled from secrets/vars |

Repository configuration it depends on (values are secrets and deliberately absent from
the repo — do not document the real ones):

| Kind | Name |
|---|---|
| Secret | `AWS_ROLE_ARN`, `AWS_CA_DOMAIN`, `AWS_CA_REPO`, `AWS_ACCOUNT_ID` |
| Variable | `AWS_REGION` |

The AWS side (role trust policy conditioned on `repo:nestauk/ahl_dwc:*`, plus
`codeartifact:GetAuthorizationToken`, `PublishPackageVersion`, `PutPackageMetadata`,
`ReadFromRepository` and `sts:GetServiceBearerToken`) is **not in this repository** and is
inferred from what the workflow calls. **Unverified** against the live IAM configuration.

Watch it:

```bash
gh run watch "$(gh run list --workflow publish-codeartifact.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```

## 5. Verify the package landed

From a machine with AWS credentials for the domain:

```bash
export AWS_REGION=<region>
aws codeartifact list-package-versions \
  --domain <domain> --domain-owner <account-id> \
  --repository <repo> --format pypi --package ahl-dwc
```

Then a real install into a scratch environment:

```bash
export UV_INDEX_URL="$(aws codeartifact get-repository-endpoint \
  --domain <domain> --domain-owner <account-id> \
  --repository <repo> --format pypi --query repositoryEndpoint --output text)simple/"
export UV_INDEX_USERNAME=aws
export UV_INDEX_PASSWORD="$(aws codeartifact get-authorization-token \
  --domain <domain> --domain-owner <account-id> \
  --query authorizationToken --output text)"

uv venv /tmp/dwc-check && VIRTUAL_ENV=/tmp/dwc-check uv pip install "ahl_dwc==0.2.0"
VIRTUAL_ENV=/tmp/dwc-check uv run python -c "import ahl_dwc, importlib.metadata as m; print(m.version('ahl_dwc'))"
```

The exact env-var names for authenticating uv against a private index, and the
`get-repository-endpoint` invocation, are **unverified** — the repository only shows the
publish direction. Cross-check against the uv and CodeArtifact docs before circulating this
to consumers. Note also that consumers on macOS/arm64 will build from the sdist and need a
compiler and CMake locally.

Caveat on history: the README still tells consumers to install with
`uv add git+https://github.com/nestauk/ahl_dwc.git --tag v0.1.0`, not from CodeArtifact.
Whether `v0.1.0` was ever successfully published is **unverified** — the tag predates the
publish workflow by about seven months.

## 6. Pre-release tags

- A Release ticked "pre-release" makes the job **skip** (`if: ${{ !github.event.release.prerelease }}`).
  A skipped job is not a failure; read it as "working as designed".
- **The guard does not hold on `workflow_dispatch`.** There is no `github.event.release` on
  that event, so the condition evaluates true and a manual dispatch will publish whatever
  tag you name, pre-release or not. Treat manual dispatch as a privileged operation.
- If you want the guard to apply to manual runs too, extend the `if` to reject tags matching
  a pre-release pattern. Not implemented today.

## 7. Manual re-run (`workflow_dispatch`)

Use when a publish failed after a green build, or to republish at a specific tag.

```bash
git show v0.2.0:pyproject.toml | grep '^version'   # confirm before dispatching
gh workflow run publish-codeartifact.yml -f tag=v0.2.0
```

Leaving `tag` blank builds the branch the workflow is dispatched from — almost never what
you want for a release.

## 8. Rollback

**You cannot unpublish.** Plan for forward fixes.

1. **Do not retry the same version.** A republish of an existing version fails; issue #9
   records exactly this, a 409 on the pre-existing 0.1.0 sdist.
2. **Bump and re-release.** Increment the patch version in `pyproject.toml`, tag, release.
   This is the supported path.
3. **Restrict the bad version in CodeArtifact.** AWS CodeArtifact supports marking a package
   version's status — `aws codeartifact update-package-versions-status --status Unlisted`
   (hides it from resolution) or `Archived` (blocks download), and
   `aws codeartifact delete-package-versions` for outright deletion. Exact behaviour of each
   status, and whether your role is permitted to call these, is **unverified here** — check
   the CodeArtifact documentation and your IAM policy before running them. There is no PyPI
   "yank" semantic in CodeArtifact.
4. **Tell consumers.** Anyone who already resolved the bad version has it in their lockfile;
   status changes do not retract it from their cache.

## Failure branches

| Symptom | Cause | Fix |
|---|---|---|
| Publish job shows as skipped | Release marked pre-release | Intended. Publish a normal Release, or dispatch manually (understanding step 6) |
| Workflow never triggered | Tag pushed but no Release published | `gh release create <tag>` |
| `uv build` fails at the CMake step | Toolchain or build-requirement resolution problem on the runner | Reproduce with `uv build` locally; see `docs/runbooks/local-development.md` |
| 401/403 immediately at `uv publish` | Almost always OIDC trust or IAM policy, not token expiry — the token is minted seconds earlier | Check the role's trust condition on `repo:nestauk/ahl_dwc:*` and the `PublishPackageVersion` permission |
| 401/403 locally, hours into a session | CodeArtifact tokens are short-lived (12 hours by default; the workflow passes no `--duration-seconds`) | Re-mint the token. Username must be `aws`, never `__token__` |
| 409 / "version already exists" | That version is already in CodeArtifact | Bump the version; see step 8 |
| Published version number is wrong | Tag and `pyproject.toml` disagreed; nothing cross-checks them | Bump and re-release; add the `git show <tag>:pyproject.toml` check to your habit |
| Consumer install fails to build on macOS/arm | Only a linux/x86_64 wheel exists; they are compiling the sdist | Ensure they have a compiler and CMake, or move the build step to cibuildwheel |
