# Design: Local Quordle engine + pluggable solver

- **Date:** 2026-08-01
- **Status:** Proposed
- **Issue:** [#1](https://github.com/robsartin/quordle-ai-experiments/issues/1)
- **ADRs:** [0012](../../adr/0012-simulation-first-evaluation.md), [0013](../../adr/0013-solver-environment-separation.md), [0014](../../adr/0014-bundled-word-lists.md), [0015](../../adr/0015-pluggable-policy-and-objective.md), [0016](../../adr/0016-jsonl-log-and-static-dashboard.md)

## Goal

Turn this repo from "an agent hand-plays Quordle in the browser and we chart it" into a
platform for **comparing solving strategies against several optimization objectives**. Two
phases:

- **Phase 1 — reach 100 logged games.** Build the engine + one baseline solver + a runner
  that simulates games and appends them to `data/quordle_games.jsonl` in the existing format,
  so the dashboard populates. Getting to 100 games becomes a single command.
- **Phase 2 — solver ideas.** A comparison harness that runs each strategy over a fixed
  answer sample and reports every objective side by side (minimize average guesses,
  guarantee-in-9, minimize maximum, minimize time-to-first-word, and a convex per-board cost).

Phase 1 is this project's build target; Phase 2 is a follow-up issue that reuses everything
Phase 1 produces.

## Non-goals (YAGNI)

- No browser automation in this work. The design *reserves the seam* for it ([ADR 13](../../adr/0013-solver-environment-separation.md)) but the browser environment is future work.
- No live web service / API. The dashboard stays a static file ([ADR 16](../../adr/0016-jsonl-log-and-static-dashboard.md)).
- No tuning of the convex-metric constants now — that needs comparison data ([ADR 15](../../adr/0015-pluggable-policy-and-objective.md)).
- No exhaustive "optimal Quordle" search. We compare *heuristic* policies, not solve the game.

## Architecture — the seam

The load-bearing decision is that the **solver never sees the answers**. It talks to an
**environment** through one narrow interface and derives everything from observable feedback:

```
Solver ──submit(guess)──▶ Environment ──returns──▶ per-board feedback for unsolved boards
       ◀────────────────                            + which boards are now solved, guesses used
```

`SimEngine` implements the interface now (holds four hidden answers). A future `BrowserEnv`
implements the same interface by typing into the live game and reading tile colors — the
solver code does not change.

### The environment interface

```
Mark    = GREEN | YELLOW | GREY
Pattern = tuple[Mark, Mark, Mark, Mark, Mark]

class TurnResult:
    guesses_used: int
    boards: list[BoardState]          # one per board, indices 0..3

class BoardState:
    index: int
    solved: bool
    solved_on: int | None             # guess number it was solved on, else None
    pattern: Pattern | None           # feedback from THIS guess if still unsolved, else None

class Environment(Protocol):
    max_guesses: int                  # 9
    def remaining_guesses(self) -> int: ...
    def finished(self) -> bool: ...   # all solved OR out of guesses
    def submit(self, guess: str) -> TurnResult: ...
```

A test double implementing `Environment` makes the solver unit-testable with no real game.

## Modules

Built in this order (each is testable before the next exists — [ADR 2](../../adr/0002-use-test-driven-development.md)):

1. **`wordlist.py`** — load the bundled answer + allowed-guess lists ([ADR 14](../../adr/0014-bundled-word-lists.md)).
   *Depends on:* the committed data files. *Used by:* engine, solver, runner.
2. **`scoring.py`** — `score(guess, answer) -> Pattern`. The green/yellow/grey rule with
   correct duplicate-letter handling (two-pass: greens, then yellows limited by remaining
   letter counts). Pure function; the first and most-tested unit. *Depends on:* nothing.
3. **`board.py`** — `Board(candidates)`; `board.filter(guess, pattern) -> Board` keeps only
   candidates `c` where `score(guess, c) == pattern`. *Depends on:* scoring.
4. **`engine.py`** — `SimEngine`: the `Environment` for four hidden answers; tracks
   `solved_on` per board, enforces the 9-guess limit, validates guesses against the
   allowed list. *Depends on:* scoring, wordlist.
5. **`policy.py`** — the `Policy` interface plus the baseline policy (below), **and** the
   objective functions (Phase 2). *Depends on:* scoring, board.
6. **`solver.py`** — drives a `Policy` against any `Environment`: maintains four `Board`
   candidate sets, loops submitting guesses and filtering until finished, records the game.
   *Depends on:* board, policy, and the environment interface (not `SimEngine` directly).
7. **`runner.py`** — `run_game(answers, policy) -> GameRecord` and
   `run_many(n, seed, policy)`; samples four distinct answers with a seeded RNG, plays via
   `SimEngine`, and appends each `GameRecord` to the JSONL log. *Depends on:* engine, solver.

New code lives under a `src/quordle/` package with a `pyproject.toml`, per
[ADR 9](../../adr/0009-python-project-layout.md); the existing `quordle_stats.py` is folded
into the package as the dashboard entry point, keeping its current CLI behavior.

## The baseline policy (Phase 1)

`Policy.choose(boards, allowed, remaining) -> str`. The baseline: **fixed openers, then
greedy expected-remaining**.

- **Openers:** a short fixed opening sequence (starting from the openers already in the log,
  e.g. `SLATE`, `CURIO`) played on the first guesses to gather broad letter coverage.
- **Greedy:** afterward, among candidate guesses, pick the one minimizing the **summed
  expected remaining candidates** across still-unsolved boards. For a guess `g` and a board's
  candidate set, partition the set by `score(g, c)`; expected remaining `= Σ_pattern(n²)/N`.
  Sum across unsolved boards; choose the minimum. Guessing a word that could itself be an
  answer is naturally favored, so boards get solved rather than merely narrowed.
- **Candidate-guess set:** to keep it fast, the baseline scores guesses drawn from the union
  of the unsolved boards' remaining candidates (full allowed-list search is a Phase-2 policy
  variant, noted not built).

This is a *good enough* solver to generate 100 sensible games; it is deliberately not the
final word — swapping it is the whole point of [ADR 15](../../adr/0015-pluggable-policy-and-objective.md).

## Data format

Reuse the existing record shape exactly ([ADR 16](../../adr/0016-jsonl-log-and-static-dashboard.md)) so
`quordle_stats.py` keeps working unchanged:

```json
{"seq": 1, "date": "2026-08-01", "mode": "sim",
 "guesses": ["SLATE", "..."], "totalGuessesUsed": 6, "maxGuesses": 9,
 "boardsSolved": 4, "won": true,
 "words": [{"board": 1, "answer": "OMEGA", "solvedOnGuess": 3}, ...]}
```

`mode` is `"sim"` for simulated games (distinct from `daily`/`practice`), so the dashboard
can distinguish them later if wanted. `solvedOnGuess` is `0` for an unsolved board.

## Objectives / metrics (Phase 2)

Pure functions over a finished `GameRecord`, all reported together for every policy:

- **avg total guesses** (on wins)
- **failure rate** (not all four solved within 9) — the "guarantee-in-9" lens
- **max guesses** / worst case
- **time-to-first-word** (guess number the first board falls)
- **convex per-board cost** — e.g. `Σ (solvedOnGuess)²` over boards, penalizing trailing
  boards so `[4,5,7,8]`=154 scores worse than `[4,5,6,8]`=141. Exact form/constants TBD from data.

The comparison harness runs each policy over a fixed, seeded answer sample and tabulates
these. Large sweeps are summarized here, not dumped game-by-game into the log.

## Testing strategy

- `scoring.py`: table-driven tests incl. duplicate-letter cases (guess has a letter twice,
  answer has it once, and vice versa) — the classic Wordle-scoring bug surface.
- `board.py`: filtering keeps exactly the consistent candidates for known (guess, pattern).
- `engine.py`: solved/unsolved tracking, `solved_on`, the 9-guess cutoff, invalid-guess
  rejection.
- `solver.py`: drive it against a **scripted test-double environment** (no real answers) to
  assert it consumes feedback and terminates correctly.
- `runner.py`: a seeded run is deterministic and emits a schema-valid JSONL line.

Coverage meets the repo gate (line > 80%, branch > 65% — [ADR 10](../../adr/0010-python-toolchain.md)).

## Build sequence

1. Scaffold: `pyproject.toml`, `src/quordle/`, `tests/`, CI wiring (Ruff, mypy, pytest,
   coverage) per ADRs 9–10; fold `quordle_stats.py` into the package.
2. Fetch + commit the canonical word lists as data files.
3. `scoring` → `board` → `engine` → `solver` (against a test double) → `policy` baseline →
   `runner`, each TDD.
4. Generate games to reach 100+; regenerate the dashboard; sanity-check the charts.
5. (Phase 2, separate issue) objective functions + comparison harness + strategy variants.

## Open questions

- Exact opener sequence and how many fixed openers before greedy kicks in — settle during
  Phase 1 with quick experiments; not architecturally significant.
- Final convex-metric form — deferred to Phase 2 with data ([ADR 15](../../adr/0015-pluggable-policy-and-objective.md)).
