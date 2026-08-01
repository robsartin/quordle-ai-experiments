---
status: Accepted
date: "2026-08-01"
topic: pluggable-policy-and-objective
tags: [architecture, solver, evaluation]
supersedes: []
related: [simulation-first-evaluation, solver-environment-separation]
---
# 15. Make guess-selection policy and optimization objective pluggable

## Context

The project exists to compare solving strategies against several distinct objectives:
minimize average guesses, guarantee a solve within nine, minimize the maximum guesses,
minimize time-to-first-word, and a **convex per-board cost** that penalizes trailing boards
(so board solves of `[4,5,7,8]` score worse than `[4,5,6,8]`). No single strategy wins on
all of them, so the design must let strategies and objectives vary independently rather than
hard-coding one of each.

## Decision

Two extension points, separately swappable:

- **Policy** — given the four candidate sets and remaining guesses, choose the next guess.
  Policies are interchangeable (e.g. fixed-openers-then-greedy; greedy expected-remaining;
  focus-fire). A policy may be told which objective to optimize.
- **Objective** — a scoring function over a finished game's per-board solve positions and
  win/loss. Every run reports **all** objective metrics regardless of which one a policy
  targeted, so strategies are compared on the full panel at once.

The comparison harness runs each policy over the fixed evaluation sample and tabulates every
metric side by side.

## Alternatives considered

- **One hard-coded strategy and metric** — rejected: defeats the project's purpose, which is
  precisely to compare alternatives.
- **A single weighted scalar objective** — rejected as the *only* view: collapsing distinct
  goals into one number hides the trade-offs we want to see; the convex weighted metric is
  offered as *one* objective among the panel, not the sole score.

## Consequences

- Adding a strategy or an objective is a new small unit, not a rewrite.
- Fair comparison is built in: all metrics are always reported for every policy.
- The convex weighted metric's exact constants are left open until comparison data exists;
  tuning them is deferred future work, not part of this decision.
