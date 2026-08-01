---
status: Accepted
date: "2026-08-01"
topic: security-baseline
tags: [universal, security]
supersedes: []
related: [privacy-and-data-handling, service-conventions]
---
# 8. Maintain a security baseline

## Context

Secrets committed to a repository are effectively public and permanent — history preserves
them even after deletion. Dependencies accumulate known vulnerabilities over time. These
risks are cheap to prevent and expensive to remediate, so we hold a non-negotiable baseline.

## Decision

Every repository upholds these practices; they are mandatory, not opt-in:

- **No secrets in the repository, ever.** Credentials, tokens, and keys are supplied via
  environment or a secret manager and never committed. Configuration templates use
  placeholders. Secret-scanning is enabled where available.
- **A documented way to supply secrets** for local development and CI, so "no secrets in
  the repo" never blocks getting the software running.
- **Automated dependency updates** (e.g. Dependabot or Renovate) raise PRs for vulnerable
  and outdated dependencies, which flow through the normal CI gate.

## Alternatives considered

- **`.gitignore` alone to keep secrets out** — relies on remembering to ignore the file
  before the first commit; one slip leaks a secret into history permanently.
- **Manual periodic dependency audits** — vulnerabilities sit unpatched between audits
  instead of surfacing continuously as they're disclosed.
- **A shared team secrets document or spreadsheet** — no environment/CI integration and no
  per-repo documented mechanism, so it doesn't scale past a handful of projects.

## Consequences

- A leaked-secret incident is prevented rather than cleaned up after the fact.
- Dependency risk is surfaced continuously instead of discovered during an audit.
- Contributors must route secrets through the sanctioned mechanism, and dependency-update
  PRs are a routine, ongoing part of maintenance.
