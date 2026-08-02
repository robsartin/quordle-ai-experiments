# Design: objective-comparison harness

- **Date:** 2026-08-02
- **Status:** Proposed
- **Issue:** [#6](https://github.com/robsartin/quordle-ai-experiments/issues/6)
- **ADR:** [0015](../../adr/0015-pluggable-policy-and-objective.md) (pluggable policy and objective)

## Goal

Score and compare solver configurations from the logged games against the **full panel** of
ADR-0015 objectives, tabulated side by side. Per ADR 0015: an objective is a scoring function
over a finished game's per-board solve positions and win/loss, and **every metric is reported
for every config** (no config wins them all — the point is to see the trade-offs).

## Objectives (per-board, over the four `solvedOnGuess` positions)

For a finished game, take its four board positions `[s1..s4]` where each is `solvedOnGuess`
(1..maxGuesses), and an **unsolved board** (`solvedOnGuess == 0`) counts as `maxGuesses + 1`
(a penalty position). Per-game scorers, one small pure function each:

- `avg_position(positions)` — mean of the four (min-avg guesses; Rob's #1).
- `max_position(positions)` — max (min-max guesses; = the last board to fall).
- `first_position(positions)` — min (time-to-first-word).
- `solved_in_nine(positions, max_guesses)` — `bool`: all four solved within `maxGuesses`
  (guarantee-in-9).
- `convex_cost(positions)` — **sum of squares** of the four positions. Provisional convex
  weighting (ADR defers the exact constants); squares penalize trailing/spread boards and
  satisfy the ADR example: `[4,5,7,8]` → 154 > `[4,5,6,8]` → 141. Marked provisional so
  retuning is a one-line change.

## Comparison

`compare(games) -> list[ConfigPanel]`:

- **Group** finished games by solver config: the key is `(player, model, assist)`, reading
  the record's `player`/`model`/`assist` fields (heuristic games have no `model`/`assist`, so
  those default to `"-"`). A readable label, e.g. `claude/claude-sonnet-5/none` or
  `heuristic`.
- **Exclude** games with `endedEarly` truthy — their board data is incomplete (we stopped
  mid-game on a stall/rejection), so they'd distort every metric. Count and report how many
  were skipped per group.
- **Aggregate** each group into a panel: game count, win rate (fraction with
  `solved_in_nine`), and the **mean over games** of each per-game metric (avg-position,
  max-position, first-position, convex-cost).

A `ConfigPanel` is a small dataclass / typed dict: `label`, `games` (scored count),
`skipped` (endedEarly count), `win_rate`, `mean_avg`, `mean_max`, `mean_first`,
`mean_convex`.

## Modules

1. **`src/quordle/objectives.py`** — **pure**, no I/O. The per-game scorers above,
   `board_positions(game) -> list[int]` (extract the four positions with the unsolved
   penalty), and `compare(games) -> list[ConfigPanel]`. Fully unit-testable.
   *Depends on:* nothing beyond the record dict shape (same `Game = dict[str, Any]` the
   dashboard uses).

2. **CLI `quordle-objectives`** (`objectives.main` + a `pyproject` entry point) — loads the
   log (reuse `dashboard.load`), runs `compare`, and prints a fixed-width table: one row per
   config, columns = the panel metrics, plus a footer noting skipped (endedEarly) games and
   that the convex column is a provisional sum-of-squares. `quordle-objectives [log]` with
   the log path defaulting to `data/quordle_games.jsonl`, matching the dashboard CLI. Exits
   with a clear message if the log has no finished games.

## Testing (offline, pure)

- Per-game scorers against known positions: `avg`/`max`/`first` on `[4,5,7,8]`; the convex
  ordering (`[4,5,7,8]` > `[4,5,6,8]`); an unsolved board (`0`) hitting the `maxGuesses + 1`
  penalty; `solved_in_nine` true/false.
- `board_positions` maps a game's `words[].solvedOnGuess` (incl. an unsolved `0`) to the
  penalty positions in board order.
- `compare`: a two-config game list (a couple of claude games + a couple of heuristic) →
  two panels with correct grouping, counts, and means; an `endedEarly` game is excluded and
  counted in `skipped`; a config whose games are all `endedEarly` still appears (0 scored)
  or is omitted — pick one: **omit configs with 0 scored games** (nothing to compare), but
  surface their skipped count in the footer.
- CLI smoke: `compare` over the bundled `data/quordle_games.sample.jsonl` (or a tmp log)
  produces a non-empty table without error.

## Mikado build sequence (green after each step)

1. `board_positions` + the five per-game scorers + their unit tests — gate green.
2. `compare` (grouping, endedEarly exclusion, aggregation) + `ConfigPanel` + tests — green.
3. `quordle-objectives` CLI (table rendering, log load, entry point) + a CLI smoke test — green.

## Non-goals (YAGNI)

- No changes to how games are played or logged; this is read-only analysis.
- No convex-constant tuning — sum-of-squares is the provisional weighting per ADR.
- No charts/HTML — a text table only (the dashboard already renders charts; this is the
  side-by-side objective panel).
- Policies targeting a specific objective (ADR's other half) is out of scope; this issue is
  only the reporting harness.
