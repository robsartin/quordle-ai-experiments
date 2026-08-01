---
status: Accepted
date: "2026-08-01"
topic: bundled-word-lists
tags: [architecture, data, solver]
supersedes: []
related: [simulation-first-evaluation]
---
# 14. Bundle canonical Wordle word lists as committed data

## Context

The engine and solver both need two word lists: the **answer list** (words that can be
solutions) and the **allowed-guess list** (valid words a player may type). Quordle's exact
lists are private and delivered inside a changeable JS bundle. The solver's behavior and
every measured metric depend on which words exist, so the source must be stable and
reproducible.

## Decision

Commit the well-known canonical Wordle lists as data files in the repository: the answer
list (~2,300 words) and the allowed-guess list (~13,000 words), fetched once at setup from a
known public source and then version-controlled. The engine draws answers from the answer
list; the solver validates guesses against the allowed-guess list. Unlike the churning game
log, these lists **are committed** — they are the fixed substrate that makes runs
reproducible.

## Alternatives considered

- **Scrape the live Quordle JS bundle** — rejected: most authentic but brittle (breaks when
  they change bundles) and requires a browser session before any offline run.
- **Derive from a system dictionary** (`/usr/share/dict/words`) — rejected: noisy; includes
  obscure and archaic words unlike Wordle's curated list, skewing solver behavior and
  metrics.

## Consequences

- Runs are deterministic and fully offline; anyone cloning the repo gets identical lists.
- Results approximate Quordle rather than matching its exact private list — an accepted
  trade recorded in [ADR 12](0012-simulation-first-evaluation.md).
- If Quordle's real lists are ever wanted, a scraped list can be added as an alternate data
  file without changing the engine or solver.
