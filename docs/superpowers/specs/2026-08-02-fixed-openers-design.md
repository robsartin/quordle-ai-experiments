# Design: fixed opening guesses (precomputed, no-recompute openers)

- **Date:** 2026-08-02
- **Status:** Proposed
- **ADRs:** [0015](../../adr/0015-pluggable-policy-and-objective.md) (pluggable policy/objective), [0017](../../adr/0017-llm-backed-policy-and-providers.md) (LLM players)

## Goal

The first 1–3 Quordle guesses are (almost) answer-independent probes, yet the LLM pays a full
API call to reinvent an opener every game. Precompute strong openers once and let a policy
play the first `N` of them with **no provider call** (the heuristic already does this;
`LLMPolicy` does not). Expose `--fixed-openers N` so the count is a knob, and make runs with
different `N` comparable in the objective harness (#6) — turning "how many fixed openers is
best?" into a measurable experiment.

## Part 1 — compute good openers (`src/quordle/openers.py`, pure + printer)

"How good is a set of openers" is scored over the **2315 possible answers** (the hidden-word
distribution). Playing fixed openers partitions the answers by their joint feedback
signature; a smaller average partition = more information.

- `signature(openers, answer) -> tuple[Pattern, ...]` — the per-opener feedback an answer
  would produce (via `quordle.scoring.score`).
- `expected_remaining(openers, answers) -> float` — mean over answers of the size of the
  answer's signature bucket (lower is better).
- `best_openers(answers, pool, k) -> list[str]` — **greedy**: pick the single opener
  minimizing `expected_remaining`; then the word that best complements it; repeat to `k`
  (brute-forcing the optimal k-tuple is infeasible). **Candidate `pool` = the full allowed
  list (12,972)** — decided 2026-08-02: this is a one-off computation, so buy the true
  optimum even if a pick is an uncommon probe word (irrelevant for an automated solver; all
  allowed words are site-accepted).
- `main()` / `python -m quordle.openers [k]` — prints the greedy top-`k` openers (and their
  `expected_remaining`) over the bundled lists, so the result is inspectable and re-derivable.
  Over the full allowed pool this takes ~2–3 min (~90M `score` calls for the trio); acceptable
  for a one-off tool.

Run it once; **hardcode the result** as a shared constant `OPENERS: tuple[str, ...]` (the
greedy top-3) in `openers.py`. If the computation confirms the current `SLATE`/`CURIO`, good;
if it finds better, those become the new shared openers.

*Depends on:* `quordle.scoring` (score/Pattern), `quordle.wordlist`.

## Part 2 — the `--fixed-openers N` knob

- **Shared `OPENERS`** (the computed top-3) is the single source of openers for both policies.
- **`LLMPolicy`** gains `openers: tuple[str, ...] = ()`. In `choose`, before building the
  prompt: `if len(history) < len(self.openers): return self.openers[len(history)]` — returns
  the pre-chosen word for this turn and **skips the provider call**. (`len(history)` is both
  the turn index and the opener index; answer-independent by construction.)
- **`FixedOpenersThenGreedy`** already supports `openers`; it will receive `OPENERS[:N]` too.
- **`build_policy_factory(player, assist, model, fixed_openers)`** passes
  `openers=OPENERS[:fixed_openers]` to whichever policy it builds, and records
  `"openers": fixed_openers` in the returned metadata (so every game logs its opener count).
- **CLI:** add `--fixed-openers N` (int, **default 2**). Default 2 keeps the heuristic's
  two-opener behavior and gives the LLM the speed/cost win by default; `--fixed-openers 0`
  recovers pure-LLM (the model picks every guess) for A/B.

## Part 3 — make the experiment comparable (`objectives.compare`)

`compare` currently groups by `(player, model, assist)`. Add the logged opener count to the
group key so `--fixed-openers 0/1/2/3` runs are **distinct rows**:

- key = `(player, model, assist, openers)` where `openers = record.get("openers")`.
- Label: append `" · o{N}"` only when the record carries an `openers` field, so pre-feature
  games (no field) keep their existing label (backward compatible).

## Testing (offline, pure — no live API)

- `expected_remaining` on a **small synthetic answer set** where the best opener is
  hand-verifiable (e.g. an answer set where one candidate perfectly splits it → remaining 1).
- `best_openers` greedily returns the expected order on that small set; a second opener
  reduces `expected_remaining` versus the first alone.
- `LLMPolicy` with `openers=("SLATE", "CURIO")`: `choose` returns `SLATE` then `CURIO` on the
  first two turns **without calling the provider** (assert via a mock provider that records
  calls / raises if called), then defers to the provider on turn 3.
- `build_policy_factory(..., fixed_openers=N)` passes `OPENERS[:N]` and logs `openers: N`;
  `--fixed-openers` parses (default 2).
- `objectives.compare` splits two otherwise-identical claude configs that differ only by
  `openers` into two rows; a record lacking the field keeps the plain label.

## Mikado build sequence (green after each step)

1. `openers.py`: `expected_remaining` + `best_openers` + printer + unit tests — green. Run the
   printer once over the full list; hardcode `OPENERS`.
2. `LLMPolicy.openers` shortcut + tests — green.
3. `--fixed-openers` wiring (`build_policy_factory` + `build_arg_parser` + metadata) + tests — green.
4. `objectives.compare` group-by-openers + tests — green.

## Non-goals (YAGNI)

- No per-board or adaptive openers — a single fixed ordered list, same every game.
- No re-tuning the greedy openers at runtime; the printer is a one-off/manual tool.
- No change to how the convex/other objectives are computed (only the grouping key gains
  `openers`).
