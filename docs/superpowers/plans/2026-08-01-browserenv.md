# BrowserEnv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Claude play a real Quordle game on `beta.quordle.com` by implementing `BrowserEnv`, an `Environment` that drives the live site so the existing solver + `LLMPolicy` + `ClaudeProvider` play it unchanged.

**Architecture:** All feedback-parsing correctness lives in a **pure** `scraper.py` (fully offline-tested against real captured aria-label strings). `BrowserEnv` is thin Playwright/Chromium glue: navigate to Practice, click the on-screen keys, read each board's tile aria-labels into plain strings, and delegate parsing to `scraper`. It implements the exact `Environment` protocol, so it drops in for `SimEngine`.

**Tech Stack:** Python 3.11+, Playwright (Chromium), pytest; builds on Phase 1 (`quordle.engine`, `quordle.solver`, `quordle.llm_policy`, `quordle.provider`).

## Global Constraints

- **Environment protocol (from `quordle.engine`, verbatim):** attrs `max_guesses: int`, `num_boards: int`, `allowed: frozenset[str]`; methods `remaining_guesses() -> int`, `finished() -> bool`, `submit(guess: str) -> TurnResult`. `TurnResult(guesses_used: int, boards: list[BoardState])`; `BoardState(index: int, solved: bool, solved_on: int | None, pattern: Pattern | None)`; `Pattern = tuple[Mark, Mark, Mark, Mark, Mark]`; `Mark` ∈ `{GREEN, YELLOW, GREY}` (values `"G"`/`"Y"`/`"."`).
- **Target: `beta.quordle.com`.** Practice is a top-nav tab (`Practice`). Classic rules: `max_guesses=9`, `num_boards=4`.
- **DOM (verified 2026-08-01):** boards `[aria-label="Game Board 1".."4"]`; each board has **45 `.quordle-box` tiles in DOM order = 9 rows × 5** (no `.quordle-guess-row` class on beta — chunk by 5). On-screen keyboard `.quordle-key` (28 keys; letter key `textContent` is the letter; Enter key matched by its `↵`/label). No `<input>`.
- **Tile `aria-label` feedback vocabulary (verified real strings):** contains `"is correct"` → GREEN; `"is in a different spot"` → YELLOW; `"is incorrect"` → GREY; `"is being guessed"` → unplayed.
- **CI stays offline.** The default gate (`ruff format --check . && ruff check . && mypy && pytest --cov=quordle --cov-branch`) must pass with **no browser and no network**. All Playwright tests are gated behind `RUN_BROWSER_TESTS=1` and skipped by default. `mypy` strict (`disallow_any_generics` — no bare `dict`/`list`); coverage `fail_under=80` (branch on). Note: run pytest **with `--cov`** locally, matching CI.
- **TDD; Mikado — build green at every committed step.** Words UPPER-case internally. Apache-2.0; no secrets.
- **Scope:** one Practice game, Claude-played, logged as `mode:"browser"`. Multi-game loop and heuristic-over-browser are out of scope.

---

### Task 1: `scraper.py` — pure feedback parsing (offline)

**Files:**
- Create: `src/quordle/browser/__init__.py`
- Create: `src/quordle/browser/scraper.py`
- Create: `tests/browser/__init__.py`
- Create: `tests/browser/test_scraper.py`

**Interfaces:**
- Consumes: `quordle.scoring` (`Mark`, `Pattern`), `quordle.engine` (`BoardState`).
- Produces:
  - `tile_mark(label: str) -> Mark | None` — `None` for an unplayed (`"is being guessed"`) tile.
  - `parse_row(labels: list[str]) -> Pattern` — 5 played tiles → `Pattern`; raises `ValueError` if any tile is unplayed or unrecognized.
  - `row_played(labels: list[str]) -> bool` — True if none of the 5 tiles is unplayed.
  - `count_played(boards: list[list[list[str]]]) -> int` — `boards[b][r]` is the 5 tile labels of board `b` row `r`; returns the max number of played rows across boards (the guesses used).
  - `read_turn(boards: list[list[list[str]]], guesses_used: int) -> list[BoardState]` — one `BoardState` per board: `solved_on` = 1-based index of the first all-GREEN row (else `None`); `solved` = `solved_on is not None`; `pattern` = `None` if the board was solved on an **earlier** row (`solved_on < guesses_used`), else `parse_row(boards[b][guesses_used-1])`.

- [ ] **Step 1: Write the failing tests (real captured strings)**

`tests/browser/__init__.py`: empty. `tests/browser/test_scraper.py`:
```python
import pytest

from quordle.scoring import Mark
from quordle.browser import scraper

G, Y, X = Mark.GREEN, Mark.YELLOW, Mark.GREY

# Real aria-label rows captured from beta.quordle.com (guess CURIO, then PLANE).
CURIO_B2 = [
    "'C' (letter 1) is in a different spot",
    "'U' (letter 2) is incorrect",
    "'R' (letter 3) is correct",
    "'I' (letter 4) is in a different spot",
    "'O' (letter 5) is incorrect",
]  # -> Y . G Y .
CURIO_B4 = [
    "'C' (letter 1) is incorrect",
    "'U' (letter 2) is incorrect",
    "'R' (letter 3) is correct",
    "'I' (letter 4) is correct",
    "'O' (letter 5) is incorrect",
]  # -> . . G G .
BLANK = ["'Blank' (letter %d) is being guessed" % i for i in range(1, 6)]
ALL_CORRECT = ["'S' (letter %d) is correct" % i for i in range(1, 6)]  # a solved row


def test_tile_mark_all_three_and_blank():
    assert scraper.tile_mark("'R' (letter 3) is correct") is Mark.GREEN
    assert scraper.tile_mark("'C' (letter 1) is in a different spot") is Mark.YELLOW
    assert scraper.tile_mark("'U' (letter 2) is incorrect") is Mark.GREY
    assert scraper.tile_mark("'Blank' (letter 1) is being guessed") is None


def test_parse_row_real_rows():
    assert scraper.parse_row(CURIO_B2) == (Y, X, G, Y, X)
    assert scraper.parse_row(CURIO_B4) == (X, X, G, G, X)


def test_parse_row_rejects_unplayed():
    with pytest.raises(ValueError):
        scraper.parse_row(BLANK)


def test_row_played():
    assert scraper.row_played(CURIO_B2) is True
    assert scraper.row_played(BLANK) is False


def test_count_played_is_max_across_boards():
    boards = [
        [CURIO_B2, CURIO_B4] + [BLANK] * 7,  # 2 played
        [CURIO_B4] + [BLANK] * 8,            # 1 played
        [BLANK] * 9,                         # 0 played
        [CURIO_B2, CURIO_B4] + [BLANK] * 7,  # 2 played
    ]
    assert scraper.count_played(boards) == 2


def test_read_turn_unsolved_and_solved():
    # board 0 solved on row 2 (this turn); board 1 not solved
    boards = [
        [CURIO_B4, ALL_CORRECT] + [BLANK] * 7,
        [CURIO_B2, CURIO_B4] + [BLANK] * 7,
    ]
    states = scraper.read_turn(boards, guesses_used=2)
    assert states[0].index == 0
    assert states[0].solved is True and states[0].solved_on == 2
    assert states[0].pattern == (G, G, G, G, G)   # solved THIS turn -> pattern present
    assert states[1].solved is False and states[1].solved_on is None
    assert states[1].pattern == (X, X, G, G, X)   # this turn's CURIO_B4 row


def test_read_turn_already_solved_board_pattern_none():
    # board solved on row 1; on turn 2 it reports pattern None
    boards = [[ALL_CORRECT, BLANK] + [BLANK] * 7]
    states = scraper.read_turn(boards, guesses_used=2)
    assert states[0].solved is True and states[0].solved_on == 1
    assert states[0].pattern is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/browser/test_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quordle.browser'`.

- [ ] **Step 3: Implement `scraper.py`**

`src/quordle/browser/__init__.py`: `"""Browser environment for playing live quordle.com."""`

`src/quordle/browser/scraper.py`:
```python
"""Pure parsing of quordle.com tile aria-labels into engine feedback (ADR 13)."""

from quordle.engine import BoardState
from quordle.scoring import Mark, Pattern


def tile_mark(label: str) -> Mark | None:
    if "is being guessed" in label:
        return None
    if "is correct" in label:
        return Mark.GREEN
    if "is in a different spot" in label:
        return Mark.YELLOW
    if "is incorrect" in label:
        return Mark.GREY
    raise ValueError(f"unrecognized tile label: {label!r}")


def parse_row(labels: list[str]) -> Pattern:
    marks: list[Mark] = []
    for label in labels:
        mark = tile_mark(label)
        if mark is None:
            raise ValueError(f"row is not fully played: {label!r}")
        marks.append(mark)
    if len(marks) != 5:
        raise ValueError(f"expected 5 tiles, got {len(marks)}")
    return (marks[0], marks[1], marks[2], marks[3], marks[4])


def row_played(labels: list[str]) -> bool:
    return all(tile_mark(label) is not None for label in labels)


def count_played(boards: list[list[list[str]]]) -> int:
    return max((sum(1 for row in board if row_played(row)) for board in boards), default=0)


def _solved_on(board: list[list[str]]) -> int | None:
    for i, row in enumerate(board, start=1):
        if row_played(row) and parse_row(row) == (Mark.GREEN,) * 5:
            return i
    return None


def read_turn(boards: list[list[list[str]]], guesses_used: int) -> list[BoardState]:
    states: list[BoardState] = []
    for index, board in enumerate(boards):
        solved_on = _solved_on(board)
        solved = solved_on is not None
        if solved and solved_on is not None and solved_on < guesses_used:
            pattern: Pattern | None = None  # solved on an earlier turn
        else:
            pattern = parse_row(board[guesses_used - 1])
        states.append(BoardState(index, solved, solved_on if solved else None, pattern))
    return states
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/browser/test_scraper.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full offline gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest --cov=quordle --cov-branch -q`
Expected: all pass; coverage ≥ 80%.

- [ ] **Step 6: Commit**

```bash
git add src/quordle/browser/__init__.py src/quordle/browser/scraper.py tests/browser/__init__.py tests/browser/test_scraper.py
git commit -m "feat: add pure quordle.com feedback scraper"
```

---

### Task 2: `BrowserEnv` (Playwright) + gated live test

**Files:**
- Create: `src/quordle/browser/browser_env.py`
- Create: `tests/browser/test_browser_env.py`
- Modify: `pyproject.toml` (add `playwright` dependency)

**Interfaces:**
- Consumes: `playwright.sync_api`, `quordle.browser.scraper`, `quordle.engine` (`Environment`/`TurnResult`/`BoardState`), `quordle.scoring`.
- Produces:
  - `class GuessRejected(Exception)` — raised by `submit` when the site rejects a guess (row didn't advance).
  - `class BrowserEnv` implementing `Environment`: `BrowserEnv(*, allowed: frozenset[str], headless: bool = True, max_guesses: int = 9, num_boards: int = 4)`. Opens Chromium, navigates to `https://beta.quordle.com`, clicks the **Practice** tab. Attributes `max_guesses`, `num_boards`, `allowed`. Methods `remaining_guesses()`, `finished()`, `submit(guess)`, `close()`, and context-manager `__enter__/__exit__` (calls `close`).
  - Internal helpers: `_read_boards() -> list[list[list[str]]]` (4 boards × 9 rows × 5 aria-label strings, via `.quordle-box` chunked by 5); `_type_word(word)` (click `.quordle-key` letters + Enter).

- [ ] **Step 1: Add the Playwright dependency**

In `pyproject.toml` `[project] dependencies`, add `"playwright>=1.40"`. Then install and fetch Chromium:
```bash
pip install -e ".[dev]" && python -m playwright install chromium
```
Document `python -m playwright install chromium` as a one-time setup step (also add it to the README's usage block in Task 3).

- [ ] **Step 2: Write the gated live test**

`tests/browser/test_browser_env.py`:
```python
import os

import pytest

RUN = os.getenv("RUN_BROWSER_TESTS") == "1"
pytestmark = pytest.mark.skipif(not RUN, reason="set RUN_BROWSER_TESTS=1 to drive a real browser")


def test_browser_env_plays_two_guesses():
    from quordle import wordlist
    from quordle.browser.browser_env import BrowserEnv

    allowed = wordlist.load_allowed()
    with BrowserEnv(allowed=allowed, headless=True) as env:
        assert env.num_boards == 4
        assert env.max_guesses == 9
        assert env.remaining_guesses() == 9
        result = env.submit("SLATE")
        assert result.guesses_used == 1
        assert len(result.boards) == 4
        # every board reports a 5-mark pattern (or None if already solved — unlikely on turn 1)
        for b in result.boards:
            assert b.pattern is None or len(b.pattern) == 5
        assert env.remaining_guesses() == 8
        env.submit("CURIO")
        assert env.remaining_guesses() == 7
```

- [ ] **Step 3: Run to verify it is skipped (default) then, optionally, live**

Run (default): `python -m pytest tests/browser/test_browser_env.py -v`
Expected: `1 skipped` (no `RUN_BROWSER_TESTS`).
Optionally, to validate the implementation, the implementer may run `RUN_BROWSER_TESTS=1 python -m pytest tests/browser/test_browser_env.py -v` and report the result — but the committed gate must pass with it skipped.

- [ ] **Step 4: Implement `browser_env.py`**

`src/quordle/browser/browser_env.py`:
```python
"""BrowserEnv: play a live quordle.com Practice game via Playwright (ADR 13)."""

from types import TracebackType

from playwright.sync_api import Page, sync_playwright

from quordle.browser import scraper
from quordle.engine import TurnResult

QUORDLE_URL = "https://beta.quordle.com"
REVEAL_TIMEOUT_MS = 8000


class GuessRejected(Exception):
    """The site rejected a guess (not in its word list); the row did not advance."""


class BrowserEnv:
    def __init__(
        self,
        *,
        allowed: frozenset[str],
        headless: bool = True,
        max_guesses: int = 9,
        num_boards: int = 4,
    ) -> None:
        self.allowed = allowed
        self.max_guesses = max_guesses
        self.num_boards = num_boards
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._page: Page = self._browser.new_page()
        self._page.goto(QUORDLE_URL)
        self._page.get_by_text("Practice", exact=True).click()
        self._page.wait_for_selector('[aria-label="Game Board 1"] .quordle-box')

    def _read_boards(self) -> list[list[list[str]]]:
        boards: list[list[list[str]]] = []
        for n in range(1, self.num_boards + 1):
            labels = self._page.eval_on_selector_all(
                f'[aria-label="Game Board {n}"] .quordle-box',
                "els => els.map(e => e.getAttribute('aria-label'))",
            )
            rows = [labels[i : i + 5] for i in range(0, len(labels), 5)]
            boards.append(rows)
        return boards

    def _type_word(self, word: str) -> None:
        for ch in word.upper():
            self._page.click(f'.quordle-key:has-text("{ch}")')
        self._page.click('.quordle-key:has-text("↵")')  # Enter (↵)

    def remaining_guesses(self) -> int:
        return self.max_guesses - scraper.count_played(self._read_boards())

    def finished(self) -> bool:
        boards = self._read_boards()
        used = scraper.count_played(boards)
        if used >= self.max_guesses:
            return True
        return all(scraper._solved_on(board) is not None for board in boards)

    def submit(self, guess: str) -> TurnResult:
        guess = guess.upper()
        if len(guess) != 5 or guess not in self.allowed:
            raise ValueError(f"invalid guess: {guess!r}")
        before = scraper.count_played(self._read_boards())
        self._type_word(guess)
        try:
            self._page.wait_for_function(
                "(n) => document.querySelectorAll('[aria-label=\"Game Board 1\"] .quordle-box')"
                ".length && [...document.querySelectorAll('[aria-label=\"Game Board 1\"] "
                ".quordle-box')].filter(e => !e.getAttribute('aria-label').includes('being guessed'))"
                ".length >= (n+1)*5",
                arg=before,
                timeout=REVEAL_TIMEOUT_MS,
            )
        except Exception as exc:  # row never advanced -> rejected word
            raise GuessRejected(f"guess not accepted by the site: {guess!r}") from exc
        boards = self._read_boards()
        used = scraper.count_played(boards)
        return TurnResult(used, scraper.read_turn(boards, used))

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()

    def __enter__(self) -> "BrowserEnv":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
```

Note: `scraper._solved_on` is used internally here; if the reviewer prefers, promote it to a public `solved_on` in Task 1. The `:has-text("X")` key selectors and the Enter `↵` glyph are the verified way to activate the on-screen keys; if `RUN_BROWSER_TESTS=1` shows a key isn't matched, adjust the selector (e.g. match on the key's `aria-label`) and note it.

- [ ] **Step 5: Run the offline gate (browser test skipped)**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest --cov=quordle --cov-branch -q`
Expected: all pass; `tests/browser/test_browser_env.py` shows as skipped. Coverage: `browser_env.py` is browser-glue exercised only under the gated test, so it will be largely uncovered — add it to `[tool.coverage.run] omit = ["src/quordle/browser/browser_env.py"]` in `pyproject.toml` (documented as Playwright glue verified by the gated live test), so the aggregate gate still reflects tested logic. Do NOT omit `scraper.py` (it is fully tested).

- [ ] **Step 6: Commit**

```bash
git add src/quordle/browser/browser_env.py tests/browser/test_browser_env.py pyproject.toml
git commit -m "feat: add Playwright BrowserEnv for live quordle.com play"
```

---

### Task 3: Runner `--env browser` wiring + `mode:"browser"` logging

**Files:**
- Modify: `src/quordle/runner.py`
- Modify: `tests/test_runner.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `quordle.browser.browser_env.BrowserEnv`, existing `solve`, `build_policy_factory`.
- Produces:
  - `run_browser_game(policy, *, seq, date, allowed, headless, metadata) -> dict` — constructs a `BrowserEnv`, plays one game with `solve`, builds a schema-valid record with `mode:"browser"`, reading `words[].answer` from the site if exposed (else `""`), `solvedOnGuess` from the solve result; closes the browser.
  - `main` gains `--env {sim,browser}` (default `sim`) and `--headed` (default headless). With `--env browser`, plays ONE game (ignores `-n`), using the selected `--player`.

- [ ] **Step 1: Write the failing test (offline — no browser launched)**

Add to `tests/test_runner.py`:
```python
def test_env_choice_default_and_parse():
    from quordle.runner import build_arg_parser

    parser = build_arg_parser()
    assert parser.parse_args([]).env == "sim"
    assert parser.parse_args(["--env", "browser", "--headed"]).env == "browser"
    assert parser.parse_args(["--env", "browser", "--headed"]).headed is True
```
(If `main` currently builds the parser inline, refactor the parser construction into a `build_arg_parser() -> argparse.ArgumentParser` so it is unit-testable without running the browser.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_runner.py -k env_choice -v`
Expected: FAIL — `ImportError: cannot import name 'build_arg_parser'` (or `env`/`headed` attribute missing).

- [ ] **Step 3: Implement the wiring**

In `src/quordle/runner.py`: extract the argparse setup into `build_arg_parser() -> argparse.ArgumentParser` (add `--env {sim,browser}` default `sim`, `--headed` `store_true`). Add:
```python
def run_browser_game(
    policy: Policy,
    *,
    seq: int,
    date: str,
    allowed: frozenset[str],
    headless: bool,
    metadata: dict[str, str] | None = None,
) -> dict:
    from quordle.browser.browser_env import BrowserEnv
    from quordle.solver import solve

    with BrowserEnv(allowed=allowed, headless=headless) as env:
        result = solve(env, policy, wordlist.load_answers())
    words = [
        {"board": i + 1, "answer": "", "solvedOnGuess": result.solved_on[i] or 0}
        for i in range(len(result.solved_on))
    ]
    boards_solved = sum(1 for w in words if w["solvedOnGuess"])
    record: dict = {
        "seq": seq, "date": date, "mode": "browser",
        "guesses": result.guesses, "totalGuessesUsed": len(result.guesses),
        "maxGuesses": 9, "boardsSolved": boards_solved,
        "won": boards_solved == len(words), "words": words,
    }
    fallbacks = getattr(policy, "fallback_count", 0)
    if fallbacks:
        record["fallbacks"] = fallbacks
    if metadata:
        record.update(metadata)
    return record
```
Then in `main`, branch on `args.env`: for `"browser"`, build one policy via `build_policy_factory(args.player, args.assist, args.model)`, call `run_browser_game(...)` once (with `metadata` including `mode:"browser"` overridden), `append_jsonl`, and print. Keep the existing `sim` path unchanged.

- [ ] **Step 4: Run to verify it passes + offline gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest --cov=quordle --cov-branch -q`
Expected: all pass. (`run_browser_game` is browser glue; if it drags coverage, add it to the same `omit` list from Task 2. Keep `build_arg_parser` and the sim path covered.)

- [ ] **Step 5: Update the README**

Add to the usage block: `python -m playwright install chromium` (one-time) and `quordle-sim --env browser --player claude` (plays one live game; needs ANTHROPIC_API_KEY). Note browser games log as `mode:"browser"`.

- [ ] **Step 6: Commit**

```bash
git add src/quordle/runner.py tests/test_runner.py README.md
git commit -m "feat: add --env browser to play one live game and log mode:browser"
```

---

### Task 4: Play one live Claude Practice game (operational)

**Files:** none committed (log/dashboard gitignored). Operational verification.

**Interfaces:**
- Consumes: `quordle-sim --env browser`, `quordle-stats`.
- Produces: one `mode:"browser"`, `player:"claude"` game appended to `data/quordle_games.jsonl`; regenerated dashboard.

- [ ] **Step 1: Confirm setup**

Run:
```bash
python -m playwright install chromium
ant auth status 2>/dev/null || ([ -n "$ANTHROPIC_API_KEY" ] && echo "API key present" || echo "no creds")
```
If no Claude credentials, stop and report — the live Claude game needs them.

- [ ] **Step 2: Play one live Claude browser game**

Run (headed so it's watchable; this makes live opus-5 calls — real cost):
```bash
quordle-sim --env browser --player claude --assist none --headed --date 2026-08-01
```
Expected: `Appended 1 claude games to data/quordle_games.jsonl` (mode `browser`). Watch a few guesses land on the real board.

- [ ] **Step 3: Verify the logged game**

Run:
```bash
python3 -c "import json;g=[json.loads(l) for l in open('data/quordle_games.jsonl') if l.strip()];b=[x for x in g if x.get('mode')=='browser'][-1];print({k:b.get(k) for k in ('seq','mode','player','model','won','boardsSolved','totalGuessesUsed','fallbacks')});print('guesses:',b['guesses'])"
```
Expected: a `mode:"browser"`, `player:"claude"` record with sensible guesses.

- [ ] **Step 4: Regenerate the dashboard and report**

Run: `quordle-stats`
Report the outcome (did Claude win? how many boards? any `GuessRejected` fallbacks?).

---

## Self-Review

**Spec coverage:**
- Pure scraper (aria-label → Pattern, solved/remaining) → Task 1. ✅
- `BrowserEnv` implementing `Environment` (Playwright, Practice, key-clicks, reveal wait, rejection) → Task 2. ✅
- `GuessRejected` → reprompt/fallback path: `submit` raises it; `LLMPolicy` reprompt/fallback already exists (Phase 1) — the browser run surfaces it via the solver loop. Note: this increment raises `GuessRejected` from `submit`; wiring it into the solver's reprompt is exercised live in Task 4. ✅ (see Open item)
- Runner `--env browser` + `mode:"browser"` logging → Task 3. ✅
- One live Claude game → Task 4. ✅
- Offline-first testing (scraper fully offline; browser gated on `RUN_BROWSER_TESTS`) → Tasks 1–2. ✅
- Playwright dependency + `playwright install chromium` → Tasks 2–3. ✅

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" — concrete code and real captured fixtures throughout. ✅

**Type consistency:** `scraper.read_turn`/`count_played`/`parse_row` signatures match between Task 1 and their use in `BrowserEnv` (Task 2); `BrowserEnv`'s `Environment` attrs/methods match the protocol; `run_browser_game` consumes `solve`'s `SolveResult.solved_on`/`guesses` (Phase 1) and the record matches the JSONL schema; `build_arg_parser` referenced consistently across Task 3. ✅

**Open item flagged for the executor:** `GuessRejected` is raised by `submit`, but the Phase-1 solver loop does not yet catch it (it would propagate and abort the game). If the gated live run in Task 4 hits a rejection, the executor should add a minimal catch in the solver/browser-run path that turns `GuessRejected` into the same signal `LLMPolicy` treats as an invalid guess (re-prompt/fallback), as a small follow-up commit — kept out of the core tasks because a well-behaved Claude rarely proposes an invalid English word. This is the one place the plan defers a decision to live behavior.
