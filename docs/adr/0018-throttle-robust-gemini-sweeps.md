---
status: Accepted
date: "2026-10-11"
topic: throttle-robust-gemini-sweeps
tags: [architecture, runner, llm, reliability]
supersedes: []
related: [llm-backed-policy-and-providers, jsonl-log-and-static-dashboard]
---
# 18. Make Gemini sweeps throttle-robust: bounded SDK retry plus top-up until N completed

## Context

Free-tier Gemini answers 429/503/504 for a large share of calls. The runner skips a
game interrupted by a transient error (ADR 17), so a fixed `-n N` sweep logs fewer
than N games. Re-running the same `--seed` to make up the difference replays the
puzzles already played and pollutes a paired comparison (issue #39).

## Decision

- **A game is _completed_ when it ran to a scored result (won or lost) and was
  logged.** A throttled or errored attempt produces no record and never counts toward
  N. The log is the source of truth: completed games are counted per config
  (`quordle.sweep.CONFIG_KEYS`), excluding `endedEarly` records.
- **Top-up sweep** (`quordle-sim --target-completed N`, sim only): keep starting games
  on fresh puzzles until the log holds N completed games for the config, with
  exponential backoff after consecutive throttles and an attempt cap
  (`--max-attempts`, default 4 per game owed). Exit status 1 if the cap leaves it short.
- **Puzzle advance and dedupe**: puzzles come from `Random(seed)`; any puzzle already
  completed in the log for the config, or already tried this run, is skipped. A re-run
  with the same seed therefore plays only the shortfall, and no puzzle repeats.
- **Provider retry**: `GeminiProvider` asks the SDK to retry 429/503/504 with a small
  attempt bound. See the code for the current numbers.
- **429 is transient**: google-genai raises it as `ClientError`, the same type as a
  bad key, so the status code decides (`runner.is_transient_error`). Other 4xx still
  fail loudly.

## Alternatives considered

- **A. Fixed-N overshoot, no code** (bump `-n` and hope) — rejected: completed count
  is still luck, and the shortfall is unobservable until after the run.
- **B alone, no provider retry** — rejected: every throttle costs a whole game; a
  retry inside the call is far cheaper.
- **C alone, no top-up** — rejected: retries shorten but do not remove the shortfall,
  and unbounded retry would mask a real outage and defeat the 150s stall backstop.
- **D. Paid tier** — not a code decision; remains available and would reduce the
  throttle rate at the source.
- **Retry the same puzzle after a throttle** — rejected: the issue asks for new
  puzzles per attempt; a puzzle-keyed dedupe also makes resume after a crash correct.
- **Top-up for `--env browser`** — rejected: live puzzles cannot be advanced or
  deduped by seed.

## Consequences

- Sweeps are resumable and idempotent per `(config, seed)`.
- Worst-case time per game is bounded by the attempt cap times the provider's
  bounded retry times the read timeout, which is large; the cap is the lever.
- Changing the record fields that identify a config (`CONFIG_KEYS`) changes which
  games count toward N.
