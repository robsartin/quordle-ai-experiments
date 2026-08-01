---
status: Accepted
date: "2026-08-01"
topic: jsonl-log-and-static-dashboard
tags: [architecture, data, reporting]
supersedes: []
related: [simulation-first-evaluation]
---
# 16. Record games as append-only JSONL; render a static HTML dashboard

## Context

Games — whether simulated or browser-played — need a durable record, and the accumulated
history needs a readable view. This decision records and keeps the format already
established in the repository so new code (the engine, solver, and runner) conforms to it
rather than inventing a parallel format.

## Decision

- **Log:** one JSON object per line in `data/quordle_games.jsonl`. Each record carries the
  guesses, per-board answers, and each board's `solvedOnGuess` (1–9, or 0 if never solved).
  Adding a game is appending a line — no schema migration, no database. The runner writes
  this same format; the log stays **gitignored** (it churns), while a committed
  `*.sample.jsonl` documents the shape.
- **Dashboard:** `quordle_stats.py` reads the log and renders a **single self-contained HTML
  file** plus PNG charts with matplotlib. No server, no runtime dependencies to view it —
  open the file in a browser.

## Alternatives considered

- **SQLite / a database** — rejected: append-only JSONL is diff-friendly, trivially
  inspectable, and needs no migrations for this scale.
- **A live web service** (e.g. Spring Boot) for the dashboard — rejected for now: a static
  file has zero runtime cost and no deployment; a live view remains possible later as a
  separate decision.

## Consequences

- Both the simulator and the future browser environment write one common log format, so the
  dashboard is agnostic to how a game was produced.
- The dashboard is portable and archivable as a single file.
- Very large simulation sweeps are summarized in the comparison harness rather than dumped
  game-by-game into the log; the log holds the games we want to keep and chart.
