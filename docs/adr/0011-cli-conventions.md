---
status: Accepted
date: "2026-08-01"
topic: cli-conventions
tags: [app-shape, cli]
supersedes: []
related: []
---
# 11. CLI conventions

## Context

Command-line tools are used by people at a terminal and by scripts and CI. A CLI that
ignores stream conventions, exit codes, or non-interactive use is painful to compose and
automate. We hold a consistent contract.

## Decision

- **Exit codes** are meaningful: `0` on success, non-zero on failure. Scripts can branch
  on them.
- **Streams are separated**: machine-consumable output goes to **stdout**; diagnostics,
  progress, and errors go to **stderr**.
- **`--help` and `--version`** are always available; `--help` is the primary documentation.
- **Configuration precedence** is explicit and consistent: command-line flags override
  environment variables, which override a config file, which overrides built-in defaults.
- **Non-interactive by default when not a TTY** — no blocking prompts and no color codes
  when output is piped; a `--yes`/`--force` flag is required for destructive actions run
  unattended.

## Alternatives considered

- **Always-interactive prompts (no TTY check)** — rejected because they hang scripts and CI
  runs that can't answer a prompt, defeating automation.
- **Config precedence left implicit or per-command** — rejected; an unstated or inconsistent
  precedence forces users to re-learn override rules for every flag and every tool.
- **Single combined output stream** — rejected; mixing machine output with diagnostics on
  stdout breaks piping and forces callers to parse around log noise.

## Consequences

- The tool composes cleanly in pipelines and CI, and its output is parseable.
- Behavior is predictable across interactive and scripted use.
- Each command carries the small obligation of TTY-aware output and precedence handling.
