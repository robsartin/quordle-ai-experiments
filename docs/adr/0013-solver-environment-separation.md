---
status: Accepted
date: "2026-08-01"
topic: solver-environment-separation
tags: [architecture, solver, interface]
supersedes: []
related: [simulation-first-evaluation, pluggable-policy-and-objective]
---
# 13. Separate the solver from the environment behind a guess interface

## Context

Two environments must play the same Quordle games: the local simulation engine (now, for
evaluation — [ADR 12](0012-simulation-first-evaluation.md)) and the live browser (soon, for
authentic games — the "hybrid" the user wants next). If solving logic were entangled with
either environment, we would maintain two copies of the strategy, and browser experiments
could not reuse the simulator's tested strategy code.

## Decision

The **solver** never accesses the hidden answers. It interacts with an **environment**
through one narrow interface: submit a guess word, receive the per-board feedback patterns
for the boards still unsolved, plus which boards are now solved and how many guesses remain.
The solver maintains its four candidate sets purely from that feedback.

- `SimEngine` implements the interface now, holding the four hidden answers.
- A future `BrowserEnv` implements the same interface by typing into the live game and
  reading the tile colors back — **no solver change required**.

## Alternatives considered

- **One class that both holds answers and picks guesses** — rejected: couples strategy to
  environment, forces a second implementation for the browser, and lets solving logic peek
  at answers, invalidating results.
- **Solver pulls candidates from the engine's internal state** — rejected: same leakage
  problem; the solver must derive everything from observable feedback, exactly as a real
  player does.

## Consequences

- Strategy code is written and tested once against the fast simulator, then reused verbatim
  in the browser hybrid.
- The interface is the contract to keep stable; environments are swappable behind it.
- A test double for the environment makes the solver unit-testable without any real game.
