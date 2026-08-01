# Design: BrowserEnv — Claude plays live quordle.com

- **Date:** 2026-08-01
- **Status:** Proposed
- **Issue:** [#7](https://github.com/robsartin/quordle-ai-experiments/issues/7)
- **ADRs:** [0013](../../adr/0013-solver-environment-separation.md) (solver/environment separation — the seam this realizes), [0017](../../adr/0017-llm-backed-policy-and-providers.md) (LLM players)
- **Builds on:** Phase 1 (issue #2, PR #4) — the `Environment` interface, `solver`, `LLMPolicy`, `ClaudeProvider`.

## Goal

Have **Claude play a real Quordle game on `beta.quordle.com`** by implementing `BrowserEnv`,
an `Environment` that drives the live site. Because everything upstream is answer-blind and
talks only to the `Environment` interface, the `solver`, `LLMPolicy`, and `ClaudeProvider`
drive the live game **unchanged** — the browser is a drop-in swap for `SimEngine` ([ADR 13](../../adr/0013-solver-environment-separation.md)).

This increment: **one Practice game, Claude-played, end-to-end, logged.**

## Non-goals (YAGNI)

- No multi-game loop (auto "new practice game") — a follow-up.
- No heuristic-over-browser — Claude is the player this increment (the heuristic still runs
  against `SimEngine`).
- No deep word-list reconciliation. If the site's true answer for a board isn't in our
  bundled answer list, that board may go unsolved — accepted this increment.
- No headed-vs-headless UX polish; default headless with a flag to watch.

## What the live-site scout established (2026-08-01)

**Target site: `beta.quordle.com`** — a standalone Quordle (same underlying codebase as the
Merriam-Webster version, but without ads/chrome). Concrete, verified facts the design depends
on (confirmed on beta; the MW site shares the same aria-label scheme, so this is portable):

- **Practice mode** (unlimited replays) uses Classic rules: **9 guesses, 4 boards**, matching
  `SimEngine` (`max_guesses=9`, `num_boards=4`). On beta it's a **top-nav tab** (`Practice`,
  next to `Daily`) — simplest possible access.
- **DOM structure (stable selectors):**
  - Four boards: `[aria-label="Game Board 1"]` … `[aria-label="Game Board 4"]` (inside
    `[aria-label="Game Boards"]` → `Game Boards Row 1/2`).
  - Each board contains **45 `.quordle-box` tiles = 9 rows × 5**, in DOM order. Rows are plain
    `div.flex.w-full` wrappers (on MW they additionally carry `.quordle-guess-row`, absent on
    beta) — so **the scraper chunks a board's `.quordle-box` list into rows of 5** rather than
    depending on a row class. Row *r* (0-indexed) is the *r*-th chunk.
  - On-screen keyboard: `.quordle-key` (28 keys); letter keys' `textContent` is the letter,
    Enter and Backspace keys identifiable by their label/symbol.
  - **There is no `<input>` element** — guesses are entered via the on-screen keyboard.
- **Feedback is in tile `aria-label` text** (semantic — preferred over the Tailwind color
  classes, though those exist too: grey `bg-gray-200`, yellow `bg-box-diff`, green
  `bg-box-correct`):
  - `"'C' (letter 1) is incorrect"` → **grey** (`Mark.GREY`).
  - `"'O' (letter 5) is in a different spot"` → **yellow** (`Mark.YELLOW`).
  - `"'X' (letter N) is correct"` → **green** (`Mark.GREEN`) — the `bg-box-correct` class is
    present; the exact "is correct" wording is confirmed at step 1 from a green tile.
  - Un-guessed tile: `"'Blank' (letter N) is being guessed"`.
- **Input works via programmatic key activation.** Raw synthetic OS keystrokes did not
  register, but dispatching clicks on the `.quordle-key` buttons did (verified by entering a
  guess). Playwright will click the keys (or use its trusted `keyboard` API if that registers).

## Architecture

```
Claude (LLMPolicy + ClaudeProvider) ──▶ solver ──▶ BrowserEnv.submit(word) ──▶ live page
                                                     ◀── per-board Patterns (scraped)
```

`BrowserEnv` implements the exact `Environment` protocol from `quordle.engine`:
`max_guesses`, `num_boards`, `allowed`, `remaining_guesses()`, `finished()`,
`submit(guess) -> TurnResult`.

## Modules (new, additive — `src/quordle/browser/`)

1. **`scraper.py`** — **pure**, no browser. The unit that turns page state into `Pattern`s,
   so it is fully unit-testable against saved DOM fixtures.
   - `parse_row(tile_labels: list[str]) -> Pattern` — map the 5 tile aria-labels of one
     filled row to a `Pattern`.
   - `board_state_from_labels(rows: list[list[str] | None], board_index, guesses_used) -> BoardState`
     — given a board's rows (each a list of 5 tile aria-labels, or `None`/empty for an
     unplayed row), produce the `BoardState` for the turn just played (solved when all five
     are correct; `solved_on = guesses_used`; `pattern` = the just-played row's pattern, or
     `None` if the board was already solved).
   - Small helpers: classify a single tile label → `Mark`; detect "board solved".
   *Depends on:* `quordle.scoring` (`Mark`/`Pattern`), `quordle.engine` (`BoardState`).

2. **`browser_env.py`** — `class BrowserEnv` implementing `Environment`.
   - Constructor opens a Playwright Chromium page, navigates to **`beta.quordle.com`**, clicks
     the **Practice** tab, and confirms an empty 4×9 board (each board's `.quordle-box` count
     is 45, all "being guessed"). Config: `headless: bool = True`, `allowed: frozenset[str]`,
     `max_guesses = 9`, `num_boards = 4`. Reads a board's row *r* by chunking its 45
     `.quordle-box` into 9 rows of 5 and taking chunk *r*.
   - `submit(guess)`: validate locally (5 letters, in `allowed`) → **enter the word** by
     clicking each letter's `.quordle-key` then the Enter key → **wait for the reveal** to
     settle → **detect rejection** (the guessed row did not advance / an error toast appeared);
     on rejection raise a dedicated `GuessRejected` error → else read all four boards' newly
     filled rows via the DOM and hand each board's tile labels to `scraper` → assemble and
     return `TurnResult`.
   - `finished()` / `remaining_guesses()`: derived from the DOM — number of filled rows and
     which boards are solved (all four solved, or 9 guesses used).
   - `close()` / context-manager support to tear down the browser.
   *Depends on:* `playwright`, `scraper`, `quordle.engine`.

3. **Runner wiring (`runner.py`):** add `--env {sim,browser}` (default `sim`) and, for
   `browser`, a `--headless/--headed` flag. `--env browser` constructs a `BrowserEnv` instead
   of `SimEngine`, plays **one** game with the chosen policy, and logs it as `mode:"browser"`
   (Claude games also carry `player`/`model`/`assist` as today). The answers, revealed by the
   site at game end, are recorded in `words[].answer` when available; otherwise left blank.

## Guess rejection & the answer-list wrinkle

- **Rejection:** the site rejects a word not in *its* dictionary; the row won't advance.
  `BrowserEnv.submit` detects this and raises `GuessRejected`. In the solver loop this is
  surfaced to the policy; `LLMPolicy` already re-prompts invalid guesses and falls back, so a
  rejected Claude guess is handled by the existing reprompt/fallback path (the runner/solver
  translates `GuessRejected` into the same "invalid guess" signal). A rejected *fallback*
  (deterministic word also rejected) is logged and the guess is skipped/counted per the site.
- **Answer outside our list:** a board whose true answer isn't in our bundled answers can't be
  pinned by candidate elimination; it may end unsolved. Accepted this increment; the record
  logs it as unsolved (`solvedOnGuess: 0`) like any loss.

## Logging

Same JSONL schema and dashboard ([ADR 16](../../adr/0016-jsonl-log-and-static-dashboard.md)),
`mode:"browser"`, plus `player`/`model`/`assist`. `data/quordle_games.jsonl` gains browser
games alongside sim games; the dashboard already ignores unknown keys and aggregates all.

## Testing (offline-first, mirrors the Claude approach)

- **`scraper` — pure unit tests, fully offline.** Capture real DOM fixtures from the live site
  (rows containing green, yellow, and grey tiles, plus a solved board and an unplayed row) and
  assert `parse_row` / `board_state_from_labels` produce the exact `Pattern`s / `BoardState`s.
  This is where correctness lives and it needs no browser.
- **`BrowserEnv` — the live end-to-end path is opt-in/gated**, exactly like the Claude live
  test: a `@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", ...)` test that launches
  Chromium, plays a couple of scripted guesses, and asserts feedback shape. **CI stays offline**
  — the browser test is skipped without the flag.
- Where practical, `submit`'s DOM-reading is tested against a **saved static page** (a captured
  Practice-game HTML with one revealed guess) loaded via `page.set_content`, so a headless run
  exercises the read path without the network.

## Dependencies

- Add `playwright` (Python) as a dependency; document `playwright install chromium` as a
  one-time setup step (and add it to CI *only* for the gated browser job, which is not run by
  default). The default gate remains offline.

## Mikado build sequence (build green at every step)

BrowserEnv is additive, so the dependency graph is shallow; the discipline is green-after-each:

1. `scraper.py` + fixtures + unit tests — `ruff`/`mypy`/`pytest` green.
2. `browser_env.py` `submit`/`finished`/`remaining` against a **saved static page**
   (`set_content`) — green.
3. Live gated integration test (`RUN_BROWSER_TESTS=1`) — green (skipped by default).
4. Runner `--env browser` wiring + `mode:"browser"` logging — green.
5. Play one live Claude Practice game; log it; regenerate the dashboard.

Each step is its own commit with the full offline gate green.

## Open questions

- Exact "correct" (green) aria-label wording — confirm from a green tile during step 1.
- Reliable **reveal-settled** signal (poll tile aria-labels until they leave the
  "being guessed" state, with a timeout) vs. a fixed delay — settle in step 2.
- Reliable **rejection** signal (error toast selector vs. "the target row's tiles are still
  blank after submit") — settle in step 2.
- How the site reveals answers at game end (for `words[].answer`) — inspect in step 5;
  blank is acceptable if not cleanly exposed.
