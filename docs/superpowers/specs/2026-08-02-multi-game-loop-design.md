# Design: BrowserEnv multi-game loop + answer capture

- **Date:** 2026-08-02
- **Status:** Proposed
- **Issue:** [#9](https://github.com/robsartin/quordle-ai-experiments/issues/9)
- **ADRs:** [0013](../../adr/0013-solver-environment-separation.md) (solver/environment separation), [0016](../../adr/0016-jsonl-log-and-static-dashboard.md) (JSONL log + dashboard)
- **Builds on:** BrowserEnv ([#7](https://github.com/robsartin/quordle-ai-experiments/issues/7)), the timeout/graceful-recovery reliability work (#14/#16/#18).

## Goal

Play **N practice games on `beta.quordle.com` in one long-lived browser**, starting a
fresh practice game between games, resilient to per-game failures, logging each game — and
capture the **real answers** the site reveals at game-over into `words[].answer`.

This replaces the external shell loop (one `quordle-sim` process + one Chromium launch per
game, plus a `pkill chromium_headless_shell` that also killed unrelated Chromium such as
Assay's). One in-app loop over one Chromium removes all of that.

## What the live scout established (2026-08-02)

Confirmed on `beta.quordle.com` Practice by playing a full game to game-over via `BrowserEnv`:

- **New game:** at game-over a results modal shows a single
  **`button[aria-label="New Practice Game"]`**. Clicking it resets the boards to 0 played
  rows (45 "being guessed" tiles) in the **same page/browser**, and `submit()` works again.
  (Note: `get_by_text("New Practice Game")` resolves to the SVG `<title>`, which is not
  clickable — match the button's `aria-label`, the same gotcha `BrowserEnv._type_word`
  already documents for the Enter key.)
- **Answers revealed at game-over:** four `[aria-label="Link to word definition"]` links whose
  innerText are the board answers (e.g. `['TRACE','QUASI','THREE','LUMPY']`), assumed in
  board order (confirm in implementation). Present on both win and loss (any site game-over);
  **absent when we end a game early ourselves** (a stall via #16), since the site never
  reached game-over.

## Architecture

```
run_browser_games(policy_factory, count=N)
  └─ one BrowserEnv (one Chromium)
       for g in 1..N:
         if g > 1: env.new_game()            # fresh puzzle, same browser
         _play_browser_game(env, policy_factory(), ...)   # existing loop (#7/#16)
         answers = env.read_answers()        # [] if we ended early
         record  = build record + words[i].answer = answers[i] when available
         append record
       (per-game try/except: one game's failure never aborts the batch)
  env.close()   # once, at the end
```

`BrowserEnv` stays an answer-blind `Environment` during play; `read_answers()` is only read
**after** a game is over, so it never leaks answers into the solver ([ADR 13](../../adr/0013-solver-environment-separation.md)).

## Components

1. **`BrowserEnv.new_game()`** — start a fresh practice game in the current page.
   - Primary: click `button[aria-label="New Practice Game"]`, then wait until the board has
     0 played rows (reuse the played-row logic already in `submit`'s reveal-wait / `scraper`).
   - Fallback (prior game ended early → no results modal, so the button is absent):
     `page.goto(QUORDLE_URL)` + click Practice + wait for the empty board.
     **Implementation step-1 scout:** confirm whether reload yields a *fresh* puzzle or
     *resumes* the partial one (localStorage). If it resumes, use an alternative reset (e.g.
     the results modal isn't required for the button — check whether "New Practice Game" is
     reachable another way, or force game-over). Document what was found.

2. **`BrowserEnv.read_answers() -> list[str]`** — at game-over, read the four
   `[aria-label="Link to word definition"]` innerTexts, uppercased, in board order. Returns
   `[]` when the site is not at game-over (e.g. our early end), so answers stay blank there.
   Pure-ish DOM read; no solver coupling.

3. **`runner.run_browser_games(policy_factory, *, count, seq, date, allowed, headless, metadata)`**
   — opens one `BrowserEnv` via the same injectable `env_factory` seam used by
   `run_browser_game` (so it's testable offline), plays `count` games as above, and returns
   the list of records. `seq` increments per game. A fresh `policy_factory()` per game gives a
   clean policy (e.g. `fallback_count`). Each game is wrapped so an unexpected error logs a
   minimal record (or is skipped with a logged note) and the loop continues.

4. **CLI (`runner.build_arg_parser` / `main`)** — add `--games N` (default `1`). With
   `--env browser` and `N > 1`, dispatch to `run_browser_games`; `N == 1` keeps today's
   `run_browser_game` path byte-for-byte. `--games` is ignored for `--env sim` (which already
   has `run_many`), or wired to it later — out of scope here.

## Logging

Same JSONL schema and dashboard ([ADR 16](../../adr/0016-jsonl-log-and-static-dashboard.md)),
`mode:"browser"`. The only change: `words[i].answer` is filled with the scraped answer when
the game reached site game-over (blank otherwise, as today). This lets analysis verify which
board was actually solved and feeds the objective-comparison harness ([#6](https://github.com/robsartin/quordle-ai-experiments/issues/6)).

## Testing (offline-first)

- **`read_answers`** — against a saved game-over page (`page.set_content` fixture) or a fake,
  assert it extracts the four answers uppercased in order, and returns `[]` when the
  definition links are absent.
- **`new_game()`** — gated live test (`RUN_BROWSER_TESTS=1`): play a game to over, call
  `new_game()`, assert the board reset to 0 played rows and a subsequent `submit()` works.
  CI stays offline (skipped without the flag).
- **`run_browser_games`** — offline via an extended `FakeBrowserEnv` that supports
  `new_game()` (reset its counters), `read_answers()` (return scripted answers), and playing
  several games; assert: N records with correct `seq`; `words[].answer` populated from the
  fake's answers; and that a game raising mid-batch still yields the remaining games
  (resilience).

## Mikado build sequence (green after each step)

1. `read_answers` + fixture/fake test — gate green.
2. `new_game()` (button primary; live gated test) + early-end fallback (after step-1 scout) — green.
3. `run_browser_games` loop against the extended `FakeBrowserEnv` — green.
4. `--games N` CLI wiring; `N==1` path unchanged — green.
5. Live 2–3-game validation (`--games 3`), confirm answers logged and one browser reused;
   regenerate the dashboard.

## Non-goals (YAGNI)

- No heuristic-over-browser multi-game (Claude is the browser player; heuristic stays on
  `SimEngine` with `run_many`).
- No parallel browsers / concurrency — one browser, sequential games.
- No retry-the-same-puzzle after an early end — we just move to a fresh game.
- No answer-list reconciliation beyond logging the scraped answer string.

## Open questions

- Reload-vs-resume semantics of the practice page (settles the `new_game()` early-end
  fallback) — step-1 scout.
- Confirm the four definition links are in board order 1–4 — step-1/step-2 scout.
