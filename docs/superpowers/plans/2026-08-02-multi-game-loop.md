# BrowserEnv Multi-Game Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Play N practice games on `beta.quordle.com` in one long-lived browser (N from the existing `--count`), starting a fresh game between games, capturing the site-revealed answers into `words[].answer`, resilient to per-game failures.

**Architecture:** One long-lived `BrowserEnv` (one Chromium). `run_browser_games` opens it once and loops: `new_game()` (except the first) → existing `_play_browser_game` → `read_answers()` → build record → append; per-game failures log-and-continue, and a `new_game()` that can't reach a fresh puzzle ends the batch gracefully. `run_browser_game` (single) becomes a `count=1` wrapper.

**Tech Stack:** Python 3.12+ (runs on pyenv 3.14.3), Playwright/Chromium, pytest.

## Global Constraints

- **Target site:** `https://beta.quordle.com` Practice (already `QUORDLE_URL` in `browser_env.py`).
- **Gate (run all before every commit):**
  - `~/.pyenv/versions/3.14.3/bin/ruff format --check .`
  - `~/.pyenv/versions/3.14.3/bin/ruff check .`
  - `~/.pyenv/versions/3.14.3/bin/mypy`
  - `~/.pyenv/versions/3.14.3/bin/pytest --cov=quordle --cov-branch --cov-report=term-missing`
  - Coverage floor: line > 80%, branch > 65%. `src/quordle/browser/browser_env.py` is **omitted** from coverage (its methods are validated by gated live tests, not the offline gate).
- **Gated live tests:** live browser tests live in `tests/browser/test_browser_env.py`, guarded by `pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", ...)`. They are skipped by default; run them with `RUN_BROWSER_TESTS=1`. Playing scripted (non-LLM) guesses is **free**.
- **ruff select:** `E, F, I, UP, B`. `except Exception` is allowed (no blind-except rule). When raising inside an `except`, use `raise ... from exc` (bugbear B904).
- **Answer-blindness (ADR 13):** `read_answers()` reads the site's revealed answers only **after** a game is over; it must never be consulted during play.

---

### Task 1: `BrowserEnv.read_answers()`

Reads the four answers the site reveals at game-over. `browser_env.py` is coverage-omitted, so this is validated by a gated live test.

**Files:**
- Modify: `src/quordle/browser/browser_env.py` (add method)
- Test: `tests/browser/test_browser_env.py` (gated live test)

**Interfaces:**
- Consumes: existing `self._page`, `REVEAL_TIMEOUT_MS`, `PlaywrightTimeoutError` (already imported).
- Produces: `BrowserEnv.read_answers(self) -> list[str]` — uppercase answers in board order, or `[]` if not at game-over.

- [ ] **Step 1: Write the failing gated test**

In `tests/browser/test_browser_env.py` (module already has `pytestmark` skipif + imports `os`, `pytest`):

```python
def test_browser_env_reads_answers_at_game_over():
    from quordle import wordlist
    from quordle.browser.browser_env import BrowserEnv, GuessRejected

    allowed = wordlist.load_allowed()
    guesses = ["SLATE", "CRANE", "MOUND", "PLUCK", "BEFIT", "WORDY", "GHOST", "JUMPY", "VEXED"]
    with BrowserEnv(allowed=allowed, headless=True) as env:
        i = 0
        while not env.finished() and i < len(guesses):
            try:
                env.submit(guesses[i])
            except GuessRejected:
                pass
            i += 1
        assert env.finished()
        answers = env.read_answers()
    assert len(answers) == 4
    assert all(len(a) == 5 and a.isalpha() and a == a.upper() for a in answers)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `RUN_BROWSER_TESTS=1 ~/.pyenv/versions/3.14.3/bin/pytest tests/browser/test_browser_env.py::test_browser_env_reads_answers_at_game_over -v`
Expected: FAIL — `AttributeError: 'BrowserEnv' object has no attribute 'read_answers'`.

- [ ] **Step 3: Implement `read_answers`**

Add to `class BrowserEnv` in `src/quordle/browser/browser_env.py` (after `finished`):

```python
    def read_answers(self) -> list[str]:
        """The four board answers the site reveals at game-over (uppercase, in
        board order), or [] if the game is not over (no results modal).

        Answer-blind (ADR 13): only read after a game ends -- never consulted
        during play.
        """
        try:
            self._page.wait_for_selector(
                '[aria-label="Link to word definition"]', timeout=REVEAL_TIMEOUT_MS
            )
        except PlaywrightTimeoutError:
            return []
        texts = self._page.eval_on_selector_all(
            '[aria-label="Link to word definition"]',
            "els => els.map(e => (e.innerText || '').trim().toUpperCase())",
        )
        return [t for t in texts if t]
```

- [ ] **Step 4: Run it to verify it passes**

Run: `RUN_BROWSER_TESTS=1 ~/.pyenv/versions/3.14.3/bin/pytest tests/browser/test_browser_env.py::test_browser_env_reads_answers_at_game_over -v`
Expected: PASS (a real game plays to over; ~30s).

- [ ] **Step 5: Run the offline gate + commit**

```bash
~/.pyenv/versions/3.14.3/bin/ruff format --check . && \
~/.pyenv/versions/3.14.3/bin/ruff check . && \
~/.pyenv/versions/3.14.3/bin/mypy && \
~/.pyenv/versions/3.14.3/bin/pytest --cov=quordle --cov-branch
git add src/quordle/browser/browser_env.py tests/browser/test_browser_env.py
git commit -m "feat: add BrowserEnv.read_answers() to capture game-over answers"
```

---

### Task 2: `BrowserEnv.new_game()`

Starts a fresh practice game in the same page via the confirmed button. Coverage-omitted; gated live test.

**Files:**
- Modify: `src/quordle/browser/browser_env.py` (add method)
- Test: `tests/browser/test_browser_env.py` (gated live test)

**Interfaces:**
- Consumes: `self._page`, `self.num_boards`, `REVEAL_TIMEOUT_MS`, `scraper.count_played`, `self._read_boards`.
- Produces: `BrowserEnv.new_game(self) -> None` — resets to a fresh game; raises `RuntimeError` if the "New Practice Game" button isn't present (game not over).

- [ ] **Step 1: Write the failing gated test**

Add to `tests/browser/test_browser_env.py`:

```python
def test_browser_env_new_game_resets_board():
    from quordle import wordlist
    from quordle.browser import scraper
    from quordle.browser.browser_env import BrowserEnv, GuessRejected

    allowed = wordlist.load_allowed()
    guesses = ["SLATE", "CRANE", "MOUND", "PLUCK", "BEFIT", "WORDY", "GHOST", "JUMPY", "VEXED"]
    with BrowserEnv(allowed=allowed, headless=True) as env:
        i = 0
        while not env.finished() and i < len(guesses):
            try:
                env.submit(guesses[i])
            except GuessRejected:
                pass
            i += 1
        assert env.finished()
        env.new_game()
        assert scraper.count_played(env._read_boards()) == 0
        env.submit("SLATE")
        assert scraper.count_played(env._read_boards()) == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `RUN_BROWSER_TESTS=1 ~/.pyenv/versions/3.14.3/bin/pytest tests/browser/test_browser_env.py::test_browser_env_new_game_resets_board -v`
Expected: FAIL — `AttributeError: ... has no attribute 'new_game'`.

- [ ] **Step 3: Implement `new_game`**

Add to `class BrowserEnv` (after `read_answers`):

```python
    def new_game(self) -> None:
        """Start a fresh practice game in the current page via the results
        modal's "New Practice Game" button (confirmed selector). Match the
        button's aria-label, not its text -- get_by_text resolves to the SVG
        <title>, which isn't clickable (same gotcha as the Enter key).

        Precondition: the game is over (the button lives in the results
        modal). Raises RuntimeError otherwise -- the caller decides what to do
        (the multi-game loop ends the batch). The early-end case (starting a
        fresh game after we ended a game early ourselves) is a deferred
        follow-up.
        """
        button = self._page.locator('button[aria-label="New Practice Game"]')
        if button.count() == 0:
            raise RuntimeError("no 'New Practice Game' button (game not over?)")
        button.first.click()
        self._page.wait_for_function(
            """
            (numBoards) => {
                const isPlayed = (label) =>
                    !!label && (
                        label.includes('is correct') ||
                        label.includes('is in a different spot') ||
                        label.includes('is incorrect')
                    );
                for (let b = 1; b <= numBoards; b++) {
                    const boxes = document.querySelectorAll(
                        `[aria-label="Game Board ${b}"] .quordle-box`
                    );
                    for (const e of boxes) {
                        if (isPlayed(e.getAttribute('aria-label'))) return false;
                    }
                }
                return true;
            }
            """,
            arg=self.num_boards,
            timeout=REVEAL_TIMEOUT_MS,
        )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `RUN_BROWSER_TESTS=1 ~/.pyenv/versions/3.14.3/bin/pytest tests/browser/test_browser_env.py::test_browser_env_new_game_resets_board -v`
Expected: PASS.

- [ ] **Step 5: Run the offline gate + commit**

```bash
~/.pyenv/versions/3.14.3/bin/ruff format --check . && \
~/.pyenv/versions/3.14.3/bin/ruff check . && \
~/.pyenv/versions/3.14.3/bin/mypy && \
~/.pyenv/versions/3.14.3/bin/pytest --cov=quordle --cov-branch
git add src/quordle/browser/browser_env.py tests/browser/test_browser_env.py
git commit -m "feat: add BrowserEnv.new_game() to start a fresh practice game"
```

---

### Task 3: Extract `_browser_record` + capture answers in the single-game path

Refactor the record-building out of `run_browser_game`, and fill `words[].answer` from `read_answers()`. Offline, coverage-counted.

**Files:**
- Modify: `src/quordle/runner.py` (extract helper; add `read_answers` to the `_ContextEnv` protocol; call it in `run_browser_game`)
- Test: `tests/test_runner.py` (extend `FakeBrowserEnv`; update the record-shape test)

**Interfaces:**
- Consumes: `SolveResult` (has `.guesses`, `.solved_on`); `_play_browser_game(env, policy, answers) -> (SolveResult, Exception | None)`.
- Produces: `_browser_record(result, ended_early, *, seq, date, answers, fallbacks, metadata) -> dict[str, Any]`; `_ContextEnv` now includes `read_answers(self) -> list[str]`.

- [ ] **Step 1: Extend `FakeBrowserEnv` and update the record-shape test (failing)**

In `tests/test_runner.py`, add a `read_answers` method to `FakeBrowserEnv` (inside the class, after `submit`):

```python
    def read_answers(self):
        return [self._answer] if self.finished() else []
```

Update `test_run_browser_game_record_shape_offline` — the answer is now captured:

```python
    assert record["words"] == [{"board": 1, "answer": "SLATE", "solvedOnGuess": 1}]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py::test_run_browser_game_record_shape_offline -v`
Expected: FAIL — record still has `"answer": ""` (capture not wired yet).

- [ ] **Step 3: Add `read_answers` to the protocol, extract `_browser_record`, wire capture**

In `src/quordle/runner.py`, add to the `_ContextEnv` protocol (after the `__exit__` stub):

```python
    def read_answers(self) -> list[str]: ...
```

Add the helper (place it just above `run_browser_game`):

```python
def _browser_record(
    result: SolveResult,
    ended_early: "Exception | None",
    *,
    seq: int,
    date: str,
    answers: list[str],
    fallbacks: int,
    metadata: dict[str, str] | None,
) -> dict[str, Any]:
    words = [
        {
            "board": i + 1,
            "answer": answers[i] if i < len(answers) else "",
            "solvedOnGuess": result.solved_on[i] or 0,
        }
        for i in range(len(result.solved_on))
    ]
    boards_solved = sum(1 for w in words if w["solvedOnGuess"])
    record: dict[str, Any] = {
        "seq": seq,
        "date": date,
        "mode": "browser",
        "guesses": result.guesses,
        "totalGuessesUsed": len(result.guesses),
        "maxGuesses": 9,
        "boardsSolved": boards_solved,
        "won": boards_solved == len(words),
        "words": words,
    }
    if ended_early is not None:
        record["endedEarly"] = True
    if fallbacks:
        record["fallbacks"] = fallbacks
    if metadata:
        record.update(metadata)
    return record
```

Replace the body of `run_browser_game` from the `with factory() as env:` line through `return record` with:

```python
    with factory() as env:
        result, ended_early = _play_browser_game(env, policy, wordlist.load_answers())
        answers = env.read_answers() if ended_early is None else []

    if ended_early is not None:
        from quordle.browser.browser_env import GuessRejected

        reason = (
            f"the site rejected a guess: {ended_early}"
            if isinstance(ended_early, GuessRejected)
            else f"a transient API error interrupted play: {ended_early!r}"
        )
        print(
            f"Browser game ended early after {len(result.guesses)} guess(es) -- "
            f"{reason}. Logging the partial result."
        )

    return _browser_record(
        result,
        ended_early,
        seq=seq,
        date=date,
        answers=answers,
        fallbacks=getattr(policy, "fallback_count", 0),
        metadata=metadata,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py -v`
Expected: PASS (record-shape test now sees `"answer": "SLATE"`; the rejected/timeout tests still pass — they end early so answers stay `[]`).

- [ ] **Step 5: Run the gate + commit**

```bash
~/.pyenv/versions/3.14.3/bin/ruff format --check . && \
~/.pyenv/versions/3.14.3/bin/ruff check . && \
~/.pyenv/versions/3.14.3/bin/mypy && \
~/.pyenv/versions/3.14.3/bin/pytest --cov=quordle --cov-branch
git add src/quordle/runner.py tests/test_runner.py
git commit -m "feat: capture site answers into words[].answer for browser games"
```

---

### Task 4: `run_browser_games` multi-game loop

One browser, N games, graceful batch-end. Offline via extended `FakeBrowserEnv`.

**Files:**
- Modify: `src/quordle/runner.py` (add `_MultiGameEnv` protocol, `run_browser_games`; make `run_browser_game` a thin `count=1` wrapper)
- Test: `tests/test_runner.py` (extend `FakeBrowserEnv` with `new_game`; add loop tests)

**Interfaces:**
- Consumes: `_browser_record`, `_play_browser_game`, `_ContextEnv` (Task 3).
- Produces: `run_browser_games(policy_factory, *, count, start_seq, date, allowed, headless, metadata=None, env_factory=None) -> list[dict[str, Any]]`; `_MultiGameEnv(_ContextEnv)` adds `new_game(self) -> None`.

- [ ] **Step 1: Extend `FakeBrowserEnv` and write the failing loop tests**

In `tests/test_runner.py`, extend `FakeBrowserEnv.__init__` with two params and a game counter (add after `self._reject_on_submit = ...`):

```python
        self._game = 1
        self._fail_on_game = fail_on_game  # 1-based game index whose submit raises
        self._new_game_fails = new_game_fails
```

Update the signature: `def __init__(self, answer, allowed, max_guesses=9, reject_on_submit=None, fail_on_game=None, new_game_fails=False):`

At the very top of `submit` (before the reject check), add:

```python
        if self._game == self._fail_on_game:
            raise RuntimeError(f"simulated browser failure on game {self._game}")
```

Add a `new_game` method (after `read_answers`):

```python
    def new_game(self):
        if self._new_game_fails:
            raise RuntimeError("cannot start new game")
        self._used = 0
        self._solved_on = None
        self._submit_calls = 0
        self._game += 1
```

Add three loop tests (after `test_browser_game_ends_gracefully_on_api_timeout`):

```python
def test_run_browser_games_plays_count_games_and_logs_answers():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=3,
        start_seq=10,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    assert [r["seq"] for r in records] == [10, 11, 12]
    assert all(r["mode"] == "browser" and r["won"] is True for r in records)
    assert all(r["words"][0]["answer"] == "SLATE" for r in records)


def test_run_browser_games_continues_after_a_game_fails():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed, fail_on_game=2)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=3,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    # game 2 raised mid-play -> skipped; games 1 and 3 still logged
    assert [r["seq"] for r in records] == [1, 3]


def test_run_browser_games_ends_batch_when_new_game_cannot_reset():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed, new_game_fails=True)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=3,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    # game 1 plays; new_game() for game 2 fails -> batch ends gracefully
    assert [r["seq"] for r in records] == [1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py -k run_browser_games -v`
Expected: FAIL — `ImportError: cannot import name 'run_browser_games'`.

- [ ] **Step 3: Add the `_MultiGameEnv` protocol and `run_browser_games`; make `run_browser_game` a wrapper**

In `src/quordle/runner.py`, add the protocol just after `_ContextEnv`:

```python
class _MultiGameEnv(_ContextEnv, Protocol):
    """A browser Environment that can also start a fresh game in place."""

    def new_game(self) -> None: ...
```

Add `run_browser_games` (after `run_browser_game`):

```python
def run_browser_games(
    policy_factory: Callable[[], Policy],
    *,
    count: int,
    start_seq: int,
    date: str,
    allowed: frozenset[str],
    headless: bool,
    metadata: dict[str, str] | None = None,
    env_factory: Callable[[], _MultiGameEnv] | None = None,
) -> list[dict[str, Any]]:
    """Play `count` practice games in ONE long-lived browser, logging each.

    Between games, new_game() starts a fresh puzzle in the same browser. A
    game that fails unexpectedly is logged-and-skipped so the batch continues;
    if new_game() cannot reach a fresh puzzle (e.g. after an early end -- a
    deferred case), the batch ends gracefully with the games completed so far.
    A fresh policy per game (via policy_factory) keeps per-game state clean.
    """
    factory = env_factory
    if factory is None:

        def _default_env_factory() -> _MultiGameEnv:
            from quordle.browser.browser_env import BrowserEnv

            return BrowserEnv(allowed=allowed, headless=headless)

        factory = _default_env_factory

    records: list[dict[str, Any]] = []
    with factory() as env:
        for offset in range(count):
            seq = start_seq + offset
            if offset > 0:
                try:
                    env.new_game()
                except Exception as exc:
                    print(
                        f"Could not start game {seq} ({exc!r}); "
                        f"ending batch after {len(records)} game(s)."
                    )
                    break
            policy = policy_factory()
            try:
                result, ended_early = _play_browser_game(
                    env, policy, wordlist.load_answers()
                )
                answers = env.read_answers() if ended_early is None else []
            except Exception as exc:
                print(f"Game {seq} failed ({exc!r}); continuing.")
                continue
            if ended_early is not None:
                print(f"Browser game {seq} ended early after {len(result.guesses)} guess(es).")
            records.append(
                _browser_record(
                    result,
                    ended_early,
                    seq=seq,
                    date=date,
                    answers=answers,
                    fallbacks=getattr(policy, "fallback_count", 0),
                    metadata=metadata,
                )
            )
    return records
```

Now make `run_browser_game` a thin `count=1` wrapper. Change its `env_factory` parameter type to `Callable[[], _MultiGameEnv] | None` and replace its whole body with:

```python
    records = run_browser_games(
        lambda: policy,
        count=1,
        start_seq=seq,
        date=date,
        allowed=allowed,
        headless=headless,
        metadata=metadata,
        env_factory=env_factory,
    )
    return records[0]
```

(The `_browser_record` helper and the early-end print now live in `run_browser_games`, so `run_browser_game`'s old body is fully replaced.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py -v`
Expected: PASS (the three new loop tests, plus the existing `run_browser_game`/rejection/timeout/progress tests still green through the wrapper).

- [ ] **Step 5: Run the gate + commit**

```bash
~/.pyenv/versions/3.14.3/bin/ruff format --check . && \
~/.pyenv/versions/3.14.3/bin/ruff check . && \
~/.pyenv/versions/3.14.3/bin/mypy && \
~/.pyenv/versions/3.14.3/bin/pytest --cov=quordle --cov-branch
git add src/quordle/runner.py tests/test_runner.py
git commit -m "feat: add run_browser_games multi-game loop (one browser, N games)"
```

---

### Task 5: Wire `--count` into the browser CLI path

Make `--env browser` honor the existing `--count` (it currently ignores it and plays one game).

**Files:**
- Modify: `src/quordle/runner.py` (`main`)
- Test: `tests/test_runner.py` (CLI dispatch test via injected `env_factory`)

**Interfaces:**
- Consumes: `run_browser_games`, `build_policy_factory`, `next_seq`, `args.count`.
- Produces: no new public symbol; behavior change only.

- [ ] **Step 1: Write the failing test**

`main()` reads `sys.argv` and builds a real BrowserEnv, so test the dispatch indirectly: assert that a browser run with `count=2` through `run_browser_games` + an injected fake yields 2 records with sequential seqs and browser metadata. Add to `tests/test_runner.py`:

```python
def test_run_browser_games_carries_browser_metadata():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=2,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        metadata={"player": "claude", "mode": "browser"},
        env_factory=lambda: env,
    )
    assert len(records) == 2
    assert all(r["player"] == "claude" and r["mode"] == "browser" for r in records)
```

- [ ] **Step 2: Run to verify it fails**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py::test_run_browser_games_carries_browser_metadata -v`
Expected: PASS already if Task 4 is complete (metadata is merged by `_browser_record`) — if so, this test just locks the behavior; proceed. If it FAILS, fix `run_browser_games` metadata wiring before continuing.

- [ ] **Step 3: Wire `main()` to `run_browser_games`**

In `src/quordle/runner.py`, replace the `if args.env == "browser":` block in `main()` with:

```python
    if args.env == "browser":
        records = run_browser_games(
            factory,
            count=args.count,
            start_seq=next_seq(args.out),
            date=args.date,
            allowed=wordlist.load_allowed(),
            headless=not args.headed,
            metadata={**metadata, "mode": "browser"},
        )
        append_jsonl(args.out, records)
        print(f"Appended {len(records)} {args.player} browser game(s) to {args.out}")
        return
```

- [ ] **Step 4: Run the gate to verify pass**

Run the full gate (ruff format --check, ruff check, mypy, pytest --cov). Expected: PASS. If `main()` browser-branch lines drop coverage below the floor, that branch is CLI glue exercised by the live validation (Task 6) — confirm total coverage is still > 80% line / > 65% branch; it should be, since only a couple of glue lines changed.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/runner.py tests/test_runner.py
git commit -m "feat: honor --count for --env browser via run_browser_games"
```

---

### Task 6: Live validation + dashboard

Validate the loop end-to-end **for free** with the heuristic player (no API cost) driving three browser games in one Chromium, then regenerate the dashboard.

**Files:** none (validation only).

- [ ] **Step 1: Run 3 heuristic browser games in one browser**

```bash
cd ~/code/quordle-ai-experiments
[ -z "$ANTHROPIC_API_KEY" ] && source ~/.zshrc 2>/dev/null
~/.pyenv/versions/3.14.3/bin/quordle-sim --env browser --player heuristic --count 3 --out data/validate.jsonl
```

Expected stdout: three games' per-guess progress lines and `Appended 3 heuristic browser game(s) to data/validate.jsonl`. (Heuristic-over-browser is used here only as a free end-to-end check of the loop/new_game/answers — it is not a shipped feature, per the spec non-goals.)

- [ ] **Step 2: Verify the log**

```bash
~/.pyenv/versions/3.14.3/bin/python -c "
import json
rows = [json.loads(l) for l in open('data/validate.jsonl')]
print('games:', len(rows), 'seqs:', [r['seq'] for r in rows])
for r in rows:
    print(r['seq'], 'won' if r['won'] else 'lost', 'answers:', [w['answer'] for w in r['words']])
"
```

Expected: 3 games, sequential seqs, each with 4 non-empty uppercase `answers`. Confirms one browser was reused across games (no per-game relaunch), `new_game()` worked between games, and answers were captured.

- [ ] **Step 3: Regenerate the dashboard**

```bash
~/.pyenv/versions/3.14.3/bin/quordle-stats --in data/validate.jsonl --out quordle_dashboard.html 2>/dev/null || \
~/.pyenv/versions/3.14.3/bin/quordle-stats
```

(Use whatever `quordle-stats` invocation the project documents; confirm it renders without error.)

- [ ] **Step 4: Clean up the scratch log (it is gitignored) and finish**

```bash
rm -f data/validate.jsonl
```

No commit (validation produced no source changes). The feature is complete.

---

## Self-Review

**Spec coverage:**
- `new_game()` (button path, RuntimeError if absent, early-end deferred) — Task 2. ✓
- `read_answers()` → `words[].answer` — Tasks 1, 3. ✓
- `run_browser_games` one-browser loop, graceful batch-end, fresh policy per game — Task 4. ✓
- `run_browser_game` becomes count=1 wrapper (shared record-building) — Tasks 3, 4. ✓
- `--count` honored by both modes (sim already; browser now) — Task 5. ✓
- Testing: `read_answers`/`new_game` gated live (Tasks 1, 2); loop offline via extended `FakeBrowserEnv` incl. mid-batch failure + new_game failure (Task 4). ✓
- Mikado order read_answers → new_game → loop → --count → live validation. ✓
- Non-goal respected: no early-end fallback; an early-ended game ends the batch (Task 4's `new_game()` RuntimeError path). ✓

**Placeholder scan:** none — every step has concrete code or an exact command.

**Type consistency:** `read_answers -> list[str]` and `new_game -> None` are declared identically in the protocols (`_ContextEnv`, `_MultiGameEnv`) and implemented in `BrowserEnv`/`FakeBrowserEnv`. `_browser_record(result, ended_early, *, seq, date, answers, fallbacks, metadata)` is called with matching keywords in both `run_browser_game` (via the wrapper → `run_browser_games`) and `run_browser_games`. `run_browser_games(..., start_seq, count, ...)` signature matches its call sites in `run_browser_game` and `main`.
