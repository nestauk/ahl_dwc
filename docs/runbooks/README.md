# Runbooks

Operational procedures for `ahl_dwc`. Each is a numbered sequence with exact commands,
expected output and a failure branch. Reach for them as follows.

| Runbook | Use when |
|---|---|
| [`local-development.md`](local-development.md) | You have a fresh clone (or a new machine) and need a green `pytest` run, or you have edited C++ and the change is not showing up. |
| [`release-and-publish.md`](release-and-publish.md) | You are cutting a version and pushing it to the private CodeArtifact PyPI, or a publish run failed and you need to recover. |
| [`ci-triage.md`](ci-triage.md) | A check is red on a pull request and you need to work out which layer broke and what to do. |
| [`upstream-sync.md`](upstream-sync.md) | Upstream `INSP-RH/bw` has changed and you need to pull the C++ across without losing the shim. |

Conventions used throughout:

- Commands assume the repository root as the working directory.
- Anything marked **unverified** could not be confirmed from the repository and needs
  checking against the live system (usually AWS or upstream GitHub) before you rely on it.
