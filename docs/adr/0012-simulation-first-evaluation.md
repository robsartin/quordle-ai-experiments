---
status: Accepted
date: "2026-08-01"
topic: simulation-first-evaluation
tags: [architecture, solver, evaluation]
supersedes: []
related: [solver-environment-separation, bundled-word-lists, pluggable-policy-and-objective]
---
# 12. Evaluate solvers by simulation against a local engine

## Context

The project's goal is to compare Quordle solving strategies against several optimization
objectives (minimize average guesses, guarantee a solve within nine, minimize the maximum,
minimize time-to-first-word, and a convex per-board cost). Answering those questions needs
many games per strategy — hundreds or thousands — with identical, repeatable conditions.

The existing games were played by an agent reasoning through guesses in the live browser,
one game at a time. That path is slow, token-expensive, and non-deterministic: it cannot
A/B two strategies over a large, fixed sample, so it cannot measure the objectives above.

## Decision

Solver experiments run against a **local, in-process Quordle engine** that draws answers
from a known word list and applies the standard green/yellow/grey feedback rule. Evaluation
sweeps a fixed sample of answer sets (up to the whole answer list), so every strategy is
measured over the same games and results are reproducible from a seed.

Live browser play is retained only as an optional showcase and as the future hybrid
environment (see [ADR 13](0013-solver-environment-separation.md)); it is **not** the
evaluation path.

## Alternatives considered

- **Browser-played evaluation** — rejected: too slow and non-deterministic to compare
  strategies over a large fixed sample; each game costs a full browser automation session.
- **Replay logged games only** — rejected: the historical log is tiny and fixed; it cannot
  test a *new* strategy against answers it never faced.

## Consequences

- Strategy comparison becomes fast, deterministic, and reproducible from a seed.
- Results reflect the bundled word list rather than Quordle's exact private list; this is an
  accepted, documented approximation (see [ADR 14](0014-bundled-word-lists.md)).
- The engine must implement the feedback rule correctly, including duplicate letters — this
  is the first unit built and tested.
