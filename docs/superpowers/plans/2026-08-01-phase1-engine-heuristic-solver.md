# Phase 1: Quordle Engine + Heuristic & Claude Solver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Quordle engine plus two players — a heuristic solver and a Claude-backed solver — that simulate games offline (heuristic) or against the live API (Claude), logging both in the existing JSONL format so we reach 100+ games and populate the dashboard.

**Architecture:** A pure scoring function feeds a candidate-filtering `Board`, a `SimEngine` environment hides four answers behind a narrow `submit()` interface, and a `Policy`-driven `solver` (answer-blind) plays. Two policies implement the same interface: `FixedOpenersThenGreedy` (heuristic) and `LLMPolicy` (renders the game state to a prompt, asks a provider for a structured guess). Providers sit behind `LLMProvider` — a scripted `MockProvider` for offline tests and a `ClaudeProvider` (official `anthropic` SDK, `claude-opus-5`, structured outputs). Gemini is Phase 2; the seam already admits it.

**Tech Stack:** Python 3.11+, `src/` layout, Ruff (lint + format), mypy, pytest, coverage.py, matplotlib (dashboard), `anthropic` + `pydantic` (Claude player).

## Global Constraints

- **Language/layout:** Python, `src/quordle/` package with `pyproject.toml` (ADR 9).
- **Toolchain (all in `pyproject.toml`, all in CI):** Ruff `check` **and** `ruff format --check` are *separate gates*; mypy; pytest; coverage.py with `branch = true`, **line coverage > 80%, branch coverage > 65%** (ADR 10).
- **TDD:** red → green → refactor → commit for every behavior (ADR 2).
- **Word lists:** bundled canonical Wordle answer + allowed-guess lists as committed data files; the **allowed** set for guess validation is `allowed-guesses ∪ answers` (ADR 14).
- **JSONL schema (exact — the dashboard depends on it):** one object per line with keys `seq`, `date`, `mode`, `guesses`, `totalGuessesUsed`, `maxGuesses`, `boardsSolved`, `won`, `words` (list of `{"board": 1..4, "answer": <UPPER>, "solvedOnGuess": 1..maxGuesses or 0}`). LLM games may add extra keys (`player`, `model`, `assist`, `fallbacks`) — the dashboard ignores unknown keys (ADR 16, 17).
- **CI stays offline and deterministic.** No test hits the network. The live Claude test runs only when `RUN_LLM_TESTS=1` is set. Heuristic runs are seeded and reproducible (ADR 12).
- **Claude specifics (ADR 17):** official `anthropic` SDK only, default model `claude-opus-5`, structured outputs via `messages.parse` with a Pydantic schema. Never an OpenAI-compatible shim.
- **Words are upper-case internally**, normalized at every boundary.
- **Log is gitignored** (`data/*.jsonl` except `*.sample.jsonl`); generated dashboard/PNGs are gitignored.
- **License:** Apache-2.0; no secrets in the repo (ADRs 7, 8).

---

### Task 1: Project scaffolding (src layout, toolchain, CI)

**Files:**
- Create: `pyproject.toml`, `src/quordle/__init__.py`, `tests/__init__.py`, `tests/test_package.py`, `.github/workflows/ci.yml`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable `quordle` package; `pytest`/`ruff`/`mypy` runnable; console scripts `quordle-sim`, `quordle-stats` reserved.

- [ ] **Step 1: Write the failing test**

`tests/test_package.py`:
```python
def test_package_imports():
    import quordle

    assert quordle.__name__ == "quordle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_package.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quordle'`.

- [ ] **Step 3: Create the package and config**

`src/quordle/__init__.py`:
```python
"""Local Quordle engine, solvers (heuristic + Claude), and simulation runner."""

__all__: list[str] = []
```

`pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "quordle-ai-experiments"
version = "0.1.0"
description = "Experiments in playing Quordle with an AI agent."
requires-python = ">=3.11"
license = "Apache-2.0"
dependencies = [
    "matplotlib>=3.5",
    "anthropic>=0.40",
    "pydantic>=2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.6", "mypy>=1.11"]

[project.scripts]
quordle-sim = "quordle.runner:main"
quordle-stats = "quordle.dashboard:main"

[tool.hatch.build.targets.wheel]
packages = ["src/quordle"]

[tool.ruff]
src = ["src", "tests"]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.11"
packages = ["quordle"]
mypy_path = "src"
strict = true

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.coverage.run]
branch = true
source = ["quordle"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

Replace `requirements.txt` contents with:
```
# Superseded by pyproject.toml. Install the project instead:
#   pip install -e ".[dev]"
matplotlib>=3.5
```

`.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: ruff format --check .
      - run: ruff check .
      - run: mypy
      - run: pytest --cov=quordle --cov-branch --cov-report=term-missing
```

- [ ] **Step 4: Install and run the full gate locally**

Run: `pip install -e ".[dev]" && ruff format --check . && ruff check . && mypy && python -m pytest -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/quordle/__init__.py tests/__init__.py tests/test_package.py .github/workflows/ci.yml requirements.txt
git commit -m "chore: scaffold src layout, toolchain, and CI gate"
```

---

### Task 2: Bundle and load the word lists

**Files:**
- Create: `src/quordle/data/answers.txt`, `src/quordle/data/allowed_guesses.txt`, `src/quordle/wordlist.py`, `tests/test_wordlist.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_answers() -> tuple[str, ...]` (upper-case, order preserved); `load_allowed() -> frozenset[str]` (`allowed-guesses ∪ answers`).

- [ ] **Step 1: Fetch the canonical lists (one-time data step)**

Run:
```bash
mkdir -p src/quordle/data
curl -fsSL https://gist.githubusercontent.com/cfreshman/a03ef2cba789d8cf00c08f767e0fad7b/raw/wordle-answers-alphabetical.txt \
  | tr '[:lower:]' '[:upper:]' | sort -u > src/quordle/data/answers.txt
curl -fsSL https://gist.githubusercontent.com/cfreshman/cdcdf777450c5b5301e439061d29694c/raw/wordle-allowed-guesses.txt \
  | tr '[:lower:]' '[:upper:]' | sort -u > src/quordle/data/allowed_guesses.txt
wc -l src/quordle/data/*.txt
```
Expected: `answers.txt` ≈ 2300 lines, `allowed_guesses.txt` ≈ 10000+ lines, each a 5-letter upper-case word. If the URLs are unreachable, stop and ask the user for an alternate source — the lists are load-bearing (ADR 14).

- [ ] **Step 2: Write the failing test**

`tests/test_wordlist.py`:
```python
from quordle import wordlist


def test_answers_are_five_letter_upper():
    answers = wordlist.load_answers()
    assert len(answers) > 2000
    assert all(len(w) == 5 and w.isupper() and w.isalpha() for w in answers)
    assert "CRANE" in answers


def test_allowed_superset_of_answers():
    answers = set(wordlist.load_answers())
    allowed = wordlist.load_allowed()
    assert answers <= allowed
    assert "SLATE" in allowed and "CURIO" in allowed
    assert all(len(w) == 5 for w in allowed)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_wordlist.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quordle.wordlist'`.

- [ ] **Step 4: Implement the loader**

`src/quordle/wordlist.py`:
```python
"""Load the bundled canonical Wordle word lists (ADR 14)."""

from functools import lru_cache
from importlib import resources


def _read(name: str) -> list[str]:
    text = resources.files("quordle.data").joinpath(name).read_text(encoding="utf-8")
    return [line.strip().upper() for line in text.splitlines() if line.strip()]


@lru_cache(maxsize=1)
def load_answers() -> tuple[str, ...]:
    return tuple(_read("answers.txt"))


@lru_cache(maxsize=1)
def load_allowed() -> frozenset[str]:
    return frozenset(_read("allowed_guesses.txt")) | frozenset(load_answers())
```

- [ ] **Step 5: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_wordlist.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/quordle/data/answers.txt src/quordle/data/allowed_guesses.txt src/quordle/wordlist.py tests/test_wordlist.py
git commit -m "feat: bundle canonical Wordle word lists and loader"
```

---

### Task 3: Scoring primitive

**Files:**
- Create: `src/quordle/scoring.py`, `tests/test_scoring.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `class Mark(Enum)` (`GREEN`/`YELLOW`/`GREY`, values `"G"`/`"Y"`/`"."`); `Pattern = tuple[Mark, Mark, Mark, Mark, Mark]`; `score(guess: str, answer: str) -> Pattern` (normalizes to upper-case).

- [ ] **Step 1: Write the failing test**

`tests/test_scoring.py`:
```python
from quordle.scoring import Mark, score

G, Y, X = Mark.GREEN, Mark.YELLOW, Mark.GREY


def test_all_green_when_equal():
    assert score("CRANE", "CRANE") == (G, G, G, G, G)


def test_greens_and_yellows():
    assert score("ARISE", "RAISE") == (Y, Y, G, G, G)


def test_duplicate_letter_in_guess_single_in_answer():
    result = score("SASSY", "BASIS")
    assert result[0] == Mark.YELLOW
    assert result[2] == Mark.GREEN
    assert result[3] == Mark.GREY


def test_case_insensitive():
    assert score("crane", "crane") == (G, G, G, G, G)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement scoring**

`src/quordle/scoring.py`:
```python
"""The Wordle green/yellow/grey scoring rule (ADR 12)."""

from collections import Counter
from enum import Enum


class Mark(Enum):
    GREEN = "G"
    YELLOW = "Y"
    GREY = "."


Pattern = tuple[Mark, Mark, Mark, Mark, Mark]


def score(guess: str, answer: str) -> Pattern:
    guess = guess.upper()
    answer = answer.upper()
    marks = [Mark.GREY] * 5
    remaining = Counter(answer)
    for i, ch in enumerate(guess):  # pass 1: greens
        if ch == answer[i]:
            marks[i] = Mark.GREEN
            remaining[ch] -= 1
    for i, ch in enumerate(guess):  # pass 2: yellows, limited by remaining count
        if marks[i] is Mark.GREEN:
            continue
        if remaining[ch] > 0:
            marks[i] = Mark.YELLOW
            remaining[ch] -= 1
    return (marks[0], marks[1], marks[2], marks[3], marks[4])
```

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/scoring.py tests/test_scoring.py
git commit -m "feat: add Wordle scoring primitive with duplicate-letter handling"
```

---

### Task 4: Candidate `Board`

**Files:**
- Create: `src/quordle/board.py`, `tests/test_board.py`

**Interfaces:**
- Consumes: `quordle.scoring.score`, `quordle.scoring.Pattern`.
- Produces: `class Board` (frozen dataclass) with `candidates: frozenset[str]`; `board.filter(guess: str, pattern: Pattern) -> Board`.

- [ ] **Step 1: Write the failing test**

`tests/test_board.py`:
```python
from quordle.board import Board
from quordle.scoring import score


def test_filter_keeps_only_consistent_candidates():
    board = Board(frozenset({"CRANE", "TRACE", "PLATE", "SLATE"}))
    pattern = score("CRANE", "TRACE")
    kept = board.filter("CRANE", pattern)
    assert "TRACE" in kept.candidates
    assert "SLATE" not in kept.candidates


def test_filter_to_single_answer():
    board = Board(frozenset({"CRANE", "TRACE"}))
    kept = board.filter("CRANE", score("CRANE", "CRANE"))
    assert kept.candidates == frozenset({"CRANE"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_board.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `Board`**

`src/quordle/board.py`:
```python
"""A single Quordle board: the answers still consistent with feedback."""

from dataclasses import dataclass

from quordle.scoring import Pattern, score


@dataclass(frozen=True)
class Board:
    candidates: frozenset[str]

    def filter(self, guess: str, pattern: Pattern) -> "Board":
        guess = guess.upper()
        return Board(frozenset(c for c in self.candidates if score(guess, c) == pattern))
```

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_board.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/board.py tests/test_board.py
git commit -m "feat: add candidate Board with feedback filtering"
```

---

### Task 5: `SimEngine` environment and feedback types

**Files:**
- Create: `src/quordle/engine.py`, `tests/test_engine.py`

**Interfaces:**
- Consumes: `quordle.scoring.score`/`Pattern`.
- Produces:
  - `@dataclass BoardState(index: int, solved: bool, solved_on: int | None, pattern: Pattern | None)`.
  - `@dataclass TurnResult(guesses_used: int, boards: list[BoardState])`.
  - `@dataclass TurnFeedback(guess: str, patterns: list[Pattern | None])` — the answer-blind record of one turn (a board already solved before this turn has `None`). Consumed by policies.
  - `class Environment(Protocol)` with attrs `max_guesses: int`, `num_boards: int`, `allowed: frozenset[str]` and methods `remaining_guesses() -> int`, `finished() -> bool`, `submit(guess: str) -> TurnResult`.
  - `class SimEngine(answers: list[str], allowed: frozenset[str], max_guesses: int = 9)` implementing `Environment`; `submit` raises `ValueError` on an invalid guess and `RuntimeError` if finished.

- [ ] **Step 1: Write the failing test**

`tests/test_engine.py`:
```python
import pytest

from quordle.engine import SimEngine
from quordle.scoring import Mark

ALLOWED = frozenset({"CRANE", "SLATE", "PLATE", "GRAPE"})


def make_engine(max_guesses=9):
    return SimEngine(["CRANE", "SLATE", "PLATE", "GRAPE"], ALLOWED, max_guesses=max_guesses)


def test_solving_a_board_records_solved_on():
    eng = make_engine()
    result = eng.submit("CRANE")
    assert result.guesses_used == 1
    assert result.boards[0].solved is True
    assert result.boards[0].solved_on == 1
    assert result.boards[0].pattern == (Mark.GREEN,) * 5
    assert result.boards[1].solved is False


def test_already_solved_board_reports_no_pattern():
    eng = make_engine()
    eng.submit("CRANE")
    result = eng.submit("SLATE")
    assert result.boards[0].solved is True
    assert result.boards[0].pattern is None


def test_invalid_guess_rejected():
    eng = make_engine()
    with pytest.raises(ValueError):
        eng.submit("ZZZZZ")
    with pytest.raises(ValueError):
        eng.submit("CAT")


def test_finished_after_max_guesses():
    eng = make_engine(max_guesses=1)
    eng.submit("GRAPE")
    assert eng.finished() is True
    assert eng.remaining_guesses() == 0
    with pytest.raises(RuntimeError):
        eng.submit("SLATE")


def test_finished_when_all_solved():
    eng = SimEngine(["CRANE", "CRANE", "CRANE", "CRANE"], ALLOWED, max_guesses=9)
    eng.submit("CRANE")
    assert eng.finished() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `SimEngine`**

`src/quordle/engine.py`:
```python
"""The simulated Quordle environment and answer-blind feedback types (ADR 13)."""

from dataclasses import dataclass
from typing import Protocol

from quordle.scoring import Pattern, score


@dataclass
class BoardState:
    index: int
    solved: bool
    solved_on: int | None
    pattern: Pattern | None


@dataclass
class TurnResult:
    guesses_used: int
    boards: list[BoardState]


@dataclass
class TurnFeedback:
    guess: str
    patterns: list[Pattern | None]  # None where the board was already solved


class Environment(Protocol):
    max_guesses: int
    num_boards: int
    allowed: frozenset[str]

    def remaining_guesses(self) -> int: ...
    def finished(self) -> bool: ...
    def submit(self, guess: str) -> TurnResult: ...


class SimEngine:
    def __init__(
        self, answers: list[str], allowed: frozenset[str], max_guesses: int = 9
    ) -> None:
        self._answers = [a.upper() for a in answers]
        self.allowed = allowed
        self.max_guesses = max_guesses
        self.num_boards = len(self._answers)
        self._used = 0
        self._solved_on: list[int | None] = [None] * self.num_boards

    def remaining_guesses(self) -> int:
        return self.max_guesses - self._used

    def finished(self) -> bool:
        return self._used >= self.max_guesses or all(s is not None for s in self._solved_on)

    def submit(self, guess: str) -> TurnResult:
        guess = guess.upper()
        if len(guess) != 5 or guess not in self.allowed:
            raise ValueError(f"invalid guess: {guess!r}")
        if self.finished():
            raise RuntimeError("game already finished")
        self._used += 1
        boards: list[BoardState] = []
        for i, answer in enumerate(self._answers):
            if self._solved_on[i] is not None:
                boards.append(BoardState(i, True, self._solved_on[i], None))
                continue
            pattern = score(guess, answer)
            if guess == answer:
                self._solved_on[i] = self._used
                boards.append(BoardState(i, True, self._used, pattern))
            else:
                boards.append(BoardState(i, False, None, pattern))
        return TurnResult(self._used, boards)
```

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/engine.py tests/test_engine.py
git commit -m "feat: add SimEngine environment and answer-blind feedback types"
```

---

### Task 6: `Policy` protocol and baseline heuristic

**Files:**
- Create: `src/quordle/policy.py`, `tests/test_policy.py`

**Interfaces:**
- Consumes: `quordle.board.Board`, `quordle.engine.TurnFeedback`, `quordle.scoring.score`.
- Produces:
  - `class Policy(Protocol)` with `choose(boards: list[Board], history: list[TurnFeedback], allowed: frozenset[str], remaining: int) -> str`. Turn index is `len(history)`.
  - `DEFAULT_OPENERS = ["SLATE", "CURIO"]`.
  - `class FixedOpenersThenGreedy(openers: list[str] | None = None)` implementing `Policy`.
  - **Solver contract:** a *solved* board arrives as an **empty** `Board` and is ignored; a board narrowed to one candidate but unsolved is guessed to solve it. Stateless.

- [ ] **Step 1: Write the failing test**

`tests/test_policy.py`:
```python
from quordle.board import Board
from quordle.engine import TurnFeedback
from quordle.policy import DEFAULT_OPENERS, FixedOpenersThenGreedy


def _fb(guess):
    return TurnFeedback(guess, [None])


def test_plays_openers_in_order():
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [Board(frozenset({"CRANE", "TRACE"}))]
    assert policy.choose(boards, [], frozenset(), remaining=9) == "SLATE"
    assert policy.choose(boards, [_fb("SLATE")], frozenset(), remaining=8) == "CURIO"


def test_greedy_solves_a_pinned_board():
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [
        Board(frozenset()),
        Board(frozenset({"GRAPE"})),
        Board(frozenset({"CRANE", "TRACE"})),
    ]
    history = [_fb("SLATE"), _fb("CURIO")]
    assert policy.choose(boards, history, frozenset(), remaining=7) == "GRAPE"


def test_greedy_is_deterministic():
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [Board(frozenset({"CRANE", "TRACE", "PLATE", "GRAPE"}))]
    history = [_fb("SLATE"), _fb("CURIO")]
    a = policy.choose(boards, history, frozenset(), remaining=7)
    b = policy.choose(boards, history, frozenset(), remaining=7)
    assert a == b


def test_default_openers_exposed():
    assert DEFAULT_OPENERS == ["SLATE", "CURIO"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_policy.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the baseline policy**

`src/quordle/policy.py`:
```python
"""Guess-selection policies (ADR 15). Phase 1 ships one heuristic baseline."""

from collections import Counter
from typing import Protocol

from quordle.board import Board
from quordle.engine import TurnFeedback
from quordle.scoring import Pattern, score

DEFAULT_OPENERS = ["SLATE", "CURIO"]


class Policy(Protocol):
    def choose(
        self,
        boards: list[Board],
        history: list[TurnFeedback],
        allowed: frozenset[str],
        remaining: int,
    ) -> str: ...


class FixedOpenersThenGreedy:
    """Fixed opening words, then a greedy expected-remaining-candidates choice.

    Solved boards arrive as empty Boards and are ignored. A one-candidate board
    is guessed to solve it. Guesses are scored only against remaining candidates
    (a fast, answer-restricted pool); ties break on sort order.
    """

    def __init__(self, openers: list[str] | None = None) -> None:
        chosen = openers if openers is not None else DEFAULT_OPENERS
        self.openers = [o.upper() for o in chosen]

    def choose(
        self,
        boards: list[Board],
        history: list[TurnFeedback],
        allowed: frozenset[str],
        remaining: int,
    ) -> str:
        if len(history) < len(self.openers):
            return self.openers[len(history)]

        active = [b for b in boards if b.candidates]
        pinned = sorted(next(iter(b.candidates)) for b in active if len(b.candidates) == 1)
        if pinned:
            return pinned[0]

        pool = sorted(set().union(*(b.candidates for b in active)))

        def expected_remaining(guess: str) -> float:
            total = 0.0
            for board in active:
                partitions: Counter[Pattern] = Counter(score(guess, c) for c in board.candidates)
                n = len(board.candidates)
                total += sum(count * count for count in partitions.values()) / n
            return total

        return min(pool, key=expected_remaining)
```

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_policy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/policy.py tests/test_policy.py
git commit -m "feat: add Policy protocol and fixed-openers-then-greedy baseline"
```

---

### Task 7: Solver loop (builds feedback history)

**Files:**
- Create: `src/quordle/solver.py`, `tests/test_solver.py`

**Interfaces:**
- Consumes: `quordle.board.Board`, `quordle.policy.Policy`, `quordle.engine.Environment`/`TurnResult`/`BoardState`/`TurnFeedback`.
- Produces: `@dataclass SolveResult(guesses: list[str], solved_on: list[int | None])`; `solve(env: Environment, policy: Policy, answers: tuple[str, ...] | list[str]) -> SolveResult`. Builds a `list[TurnFeedback]` and passes it to `policy.choose`; collapses solved boards to empty.

- [ ] **Step 1: Write the failing test**

`tests/test_solver.py`:
```python
from quordle.engine import BoardState, TurnResult
from quordle.scoring import score
from quordle.solver import solve


class ScriptedEnv:
    """A one-board environment with a fixed hidden answer, for solver testing."""

    def __init__(self, answer, allowed, max_guesses=9):
        self._answer = answer.upper()
        self.allowed = allowed
        self.max_guesses = max_guesses
        self.num_boards = 1
        self._used = 0
        self._solved_on = None

    def remaining_guesses(self):
        return self.max_guesses - self._used

    def finished(self):
        return self._used >= self.max_guesses or self._solved_on is not None

    def submit(self, guess):
        guess = guess.upper()
        self._used += 1
        if self._solved_on is not None:
            return TurnResult(self._used, [BoardState(0, True, self._solved_on, None)])
        pattern = score(guess, self._answer)
        if guess == self._answer:
            self._solved_on = self._used
            return TurnResult(self._used, [BoardState(0, True, self._used, pattern)])
        return TurnResult(self._used, [BoardState(0, False, None, pattern)])


class FixedGuessPolicy:
    def __init__(self, guesses):
        self._guesses = guesses

    def choose(self, boards, history, allowed, remaining):
        return self._guesses[len(history)]


def test_solve_records_guesses_and_solved_on():
    allowed = frozenset({"SLATE", "CRANE"})
    env = ScriptedEnv("CRANE", allowed)
    result = solve(env, FixedGuessPolicy(["SLATE", "CRANE"]), ["SLATE", "CRANE"])
    assert result.guesses == ["SLATE", "CRANE"]
    assert result.solved_on == [2]


def test_solve_stops_at_max_guesses_when_unsolved():
    allowed = frozenset({"SLATE", "CRANE"})
    env = ScriptedEnv("CRANE", allowed, max_guesses=1)
    result = solve(env, FixedGuessPolicy(["SLATE"]), ["SLATE", "CRANE"])
    assert result.guesses == ["SLATE"]
    assert result.solved_on == [None]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_solver.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the solver**

`src/quordle/solver.py`:
```python
"""Drive a Policy against any Environment, answer-blind (ADR 13)."""

from dataclasses import dataclass

from quordle.board import Board
from quordle.engine import Environment, TurnFeedback
from quordle.policy import Policy


@dataclass
class SolveResult:
    guesses: list[str]
    solved_on: list[int | None]


def solve(env: Environment, policy: Policy, answers: tuple[str, ...] | list[str]) -> SolveResult:
    full = frozenset(w.upper() for w in answers)
    boards = [Board(full) for _ in range(env.num_boards)]
    guesses: list[str] = []
    history: list[TurnFeedback] = []
    solved_on: list[int | None] = [None] * env.num_boards

    while not env.finished():
        guess = policy.choose(boards, history, env.allowed, env.remaining_guesses())
        guesses.append(guess)
        result = env.submit(guess)
        history.append(TurnFeedback(guess, [state.pattern for state in result.boards]))
        for i, state in enumerate(result.boards):
            if state.solved:
                if solved_on[i] is None:
                    solved_on[i] = state.solved_on
                boards[i] = Board(frozenset())
            elif state.pattern is not None:
                boards[i] = boards[i].filter(guess, state.pattern)

    return SolveResult(guesses, solved_on)
```

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_solver.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/solver.py tests/test_solver.py
git commit -m "feat: add answer-blind solver loop with feedback history"
```

---

### Task 8: Runner — play games and append JSONL

**Files:**
- Create: `src/quordle/runner.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `quordle.wordlist`, `quordle.engine.SimEngine`, `quordle.solver.solve`, `quordle.policy.FixedOpenersThenGreedy`/`Policy`.
- Produces:
  - `sample_answers(rng: random.Random, answers: tuple[str, ...], count: int = 4) -> list[str]`.
  - `run_game(answers, policy, *, seq, date, allowed, max_guesses=9, mode="sim", metadata=None) -> dict` — schema-valid record; merges `metadata` and, if `policy.fallback_count > 0`, adds `"fallbacks"`.
  - `run_many(count, *, seed, policy_factory, answers, allowed, start_seq, date, metadata=None) -> list[dict]` — a fresh policy per game (LLM policies are stateful).
  - `append_jsonl(path: str, records: list[dict]) -> None`.
  - `main() -> None` — CLI `quordle-sim` (heuristic only in this task; Claude wiring is added in Task 11).

- [ ] **Step 1: Write the failing test**

`tests/test_runner.py`:
```python
import json
import random

from quordle import wordlist
from quordle.policy import FixedOpenersThenGreedy
from quordle.runner import append_jsonl, run_game, run_many, sample_answers


def test_sample_answers_distinct():
    picks = sample_answers(random.Random(1), wordlist.load_answers(), count=4)
    assert len(picks) == 4 and len(set(picks)) == 4


def test_run_game_produces_schema_valid_record():
    record = run_game(
        ["CRANE", "SLATE", "PLATE", "GRAPE"],
        FixedOpenersThenGreedy(),
        seq=1,
        date="2026-08-01",
        allowed=wordlist.load_allowed(),
    )
    assert record["seq"] == 1 and record["mode"] == "sim" and record["maxGuesses"] == 9
    assert record["totalGuessesUsed"] == len(record["guesses"])
    assert len(record["words"]) == 4
    for i, w in enumerate(record["words"], start=1):
        assert w["board"] == i and w["answer"].isupper()
        assert isinstance(w["solvedOnGuess"], int)
    assert record["boardsSolved"] == sum(1 for w in record["words"] if w["solvedOnGuess"])
    assert record["won"] == (record["boardsSolved"] == 4)


def test_run_game_merges_metadata():
    record = run_game(
        ["CRANE", "SLATE", "PLATE", "GRAPE"],
        FixedOpenersThenGreedy(),
        seq=1,
        date="2026-08-01",
        allowed=wordlist.load_allowed(),
        metadata={"player": "heuristic"},
    )
    assert record["player"] == "heuristic"


def test_run_many_deterministic_for_a_seed():
    answers, allowed = wordlist.load_answers(), wordlist.load_allowed()
    a = run_many(3, seed=7, policy_factory=FixedOpenersThenGreedy, answers=answers,
                 allowed=allowed, start_seq=1, date="2026-08-01")
    b = run_many(3, seed=7, policy_factory=FixedOpenersThenGreedy, answers=answers,
                 allowed=allowed, start_seq=1, date="2026-08-01")
    assert [g["words"] for g in a] == [g["words"] for g in b]


def test_append_jsonl_round_trips(tmp_path):
    path = tmp_path / "games.jsonl"
    records = [{"seq": 1, "guesses": ["SLATE"]}]
    append_jsonl(str(path), records)
    append_jsonl(str(path), records)
    lines = path.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["seq"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the runner**

`src/quordle/runner.py`:
```python
"""Play games and append them to the JSONL log (ADR 16)."""

import argparse
import json
import random
from collections.abc import Callable

from quordle import wordlist
from quordle.engine import SimEngine
from quordle.policy import FixedOpenersThenGreedy, Policy
from quordle.solver import solve

DEFAULT_LOG = "data/quordle_games.jsonl"


def sample_answers(rng: random.Random, answers: tuple[str, ...], count: int = 4) -> list[str]:
    return rng.sample(list(answers), count)


def run_game(
    answers: list[str],
    policy: Policy,
    *,
    seq: int,
    date: str,
    allowed: frozenset[str],
    max_guesses: int = 9,
    mode: str = "sim",
    metadata: dict | None = None,
) -> dict:
    answers = [a.upper() for a in answers]
    engine = SimEngine(answers, allowed, max_guesses=max_guesses)
    result = solve(engine, policy, wordlist.load_answers())
    words = [
        {"board": i + 1, "answer": answers[i], "solvedOnGuess": result.solved_on[i] or 0}
        for i in range(len(answers))
    ]
    boards_solved = sum(1 for w in words if w["solvedOnGuess"])
    record: dict = {
        "seq": seq,
        "date": date,
        "mode": mode,
        "guesses": result.guesses,
        "totalGuessesUsed": len(result.guesses),
        "maxGuesses": max_guesses,
        "boardsSolved": boards_solved,
        "won": boards_solved == len(answers),
        "words": words,
    }
    fallbacks = getattr(policy, "fallback_count", 0)
    if fallbacks:
        record["fallbacks"] = fallbacks
    if metadata:
        record.update(metadata)
    return record


def run_many(
    count: int,
    *,
    seed: int,
    policy_factory: Callable[[], Policy],
    answers: tuple[str, ...],
    allowed: frozenset[str],
    start_seq: int,
    date: str,
    metadata: dict | None = None,
) -> list[dict]:
    rng = random.Random(seed)
    records: list[dict] = []
    for offset in range(count):
        picks = sample_answers(rng, answers, count=4)
        records.append(
            run_game(
                picks,
                policy_factory(),
                seq=start_seq + offset,
                date=date,
                allowed=allowed,
                metadata=metadata,
            )
        )
    return records


def append_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def next_seq(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            seqs = [json.loads(line)["seq"] for line in fh if line.strip()]
        return max(seqs, default=0) + 1
    except FileNotFoundError:
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate Quordle games and log them.")
    parser.add_argument("-n", "--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=DEFAULT_LOG)
    parser.add_argument("--date", default="2026-08-01")
    args = parser.parse_args()

    records = run_many(
        args.count,
        seed=args.seed,
        policy_factory=FixedOpenersThenGreedy,
        answers=wordlist.load_answers(),
        allowed=wordlist.load_allowed(),
        start_seq=next_seq(args.out),
        date=args.date,
        metadata={"player": "heuristic"},
    )
    append_jsonl(args.out, records)
    print(f"Appended {len(records)} games to {args.out}")


if __name__ == "__main__":
    main()
```

Note: `--date` defaults to a fixed placeholder so runs stay deterministic and no wall-clock call is needed.

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/runner.py tests/test_runner.py
git commit -m "feat: add simulation runner and quordle-sim CLI (heuristic)"
```

---

### Task 9: LLM provider abstraction (mock + Claude)

**Files:**
- Create: `src/quordle/provider.py`, `tests/test_provider.py`

**Interfaces:**
- Consumes: `anthropic`, `pydantic` (Claude only).
- Produces:
  - `class GuessResponse(BaseModel)` with `reasoning: str`, `guess: str`.
  - `class LLMProvider(Protocol)` with `next_guess(prompt: str) -> GuessResponse`.
  - `class MockProvider(guesses: list[str], reasoning: str = "scripted")` — returns scripted guesses in order (repeating the last when exhausted); for offline tests and reprompt simulation.
  - `class ClaudeProvider(model: str = "claude-opus-5", max_tokens: int = 4096)` — official `anthropic` SDK, `messages.parse` with `output_format=GuessResponse` (ADR 17). Constructs offline; only `next_guess` hits the network.

- [ ] **Step 1: Write the failing test** (offline — MockProvider + schema only)

`tests/test_provider.py`:
```python
from quordle.provider import GuessResponse, MockProvider


def test_guess_response_schema():
    r = GuessResponse(reasoning="because", guess="CRANE")
    assert r.guess == "CRANE"


def test_mock_provider_returns_scripted_guesses_in_order():
    provider = MockProvider(["CRANE", "SLATE"])
    assert provider.next_guess("prompt").guess == "CRANE"
    assert provider.next_guess("prompt").guess == "SLATE"
    assert provider.next_guess("prompt").guess == "SLATE"  # repeats the last
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quordle.provider'`.

- [ ] **Step 3: Implement the providers**

`src/quordle/provider.py`:
```python
"""LLM providers behind one interface (ADR 17): a scripted mock and Claude."""

from typing import Protocol

from pydantic import BaseModel


class GuessResponse(BaseModel):
    reasoning: str
    guess: str


class LLMProvider(Protocol):
    def next_guess(self, prompt: str) -> GuessResponse: ...


class MockProvider:
    """Scripted provider for offline tests; repeats the final guess when exhausted."""

    def __init__(self, guesses: list[str], reasoning: str = "scripted") -> None:
        self._guesses = [g.upper() for g in guesses]
        self._reasoning = reasoning
        self._index = 0

    def next_guess(self, prompt: str) -> GuessResponse:
        guess = self._guesses[min(self._index, len(self._guesses) - 1)]
        self._index += 1
        return GuessResponse(reasoning=self._reasoning, guess=guess)


class ClaudeProvider:
    """Claude via the official anthropic SDK, structured outputs, default claude-opus-5."""

    def __init__(self, model: str = "claude-opus-5", max_tokens: int = 4096) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def next_guess(self, prompt: str) -> GuessResponse:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_format=GuessResponse,
        )
        if response.parsed_output is None:
            raise RuntimeError("Claude returned no structured output")
        return response.parsed_output
```

- [ ] **Step 4: Add the live, opt-in Claude test**

Append to `tests/test_provider.py`:
```python
import os

import pytest


@pytest.mark.skipif(os.getenv("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1 to hit the live API")
def test_claude_provider_returns_a_five_letter_word():
    from quordle.provider import ClaudeProvider

    resp = ClaudeProvider().next_guess(
        "Reply with any common 5-letter English word as your guess."
    )
    assert len(resp.guess.strip()) == 5
```

- [ ] **Step 5: Run the gate (offline)**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_provider.py -v`
Expected: PASS; the live test is SKIPPED (no `RUN_LLM_TESTS`).

- [ ] **Step 6: Commit**

```bash
git add src/quordle/provider.py tests/test_provider.py
git commit -m "feat: add LLMProvider abstraction with mock and Claude implementations"
```

---

### Task 10: `LLMPolicy` — render state, parse guess, reprompt, fall back

**Files:**
- Create: `src/quordle/llm_policy.py`, `tests/test_llm_policy.py`

**Interfaces:**
- Consumes: `quordle.board.Board`, `quordle.engine.TurnFeedback`, `quordle.scoring.Mark`, `quordle.provider.LLMProvider`.
- Produces:
  - `class Assist(Enum)` — `NONE`/`CONSTRAINTS`/`CANDIDATES` (values `"none"`/`"constraints"`/`"candidates"`).
  - `CANDIDATE_THRESHOLD = 20`.
  - `render_prompt(boards, history, assist, remaining) -> str`.
  - `class LLMPolicy(provider: LLMProvider, *, assist: Assist = Assist.NONE, max_retries: int = 2)` implementing `Policy`; exposes `fallback_count: int`. `choose` re-prompts an invalid guess up to `max_retries` times, then submits a deterministic valid fallback and increments `fallback_count`.

- [ ] **Step 1: Write the failing test**

`tests/test_llm_policy.py`:
```python
from quordle.board import Board
from quordle.engine import TurnFeedback
from quordle.llm_policy import Assist, LLMPolicy, render_prompt
from quordle.provider import MockProvider
from quordle.scoring import Mark

ALLOWED = frozenset({"CRANE", "SLATE", "GRAPE"})
G, Y, X = Mark.GREEN, Mark.YELLOW, Mark.GREY


def test_returns_valid_provider_guess():
    policy = LLMPolicy(MockProvider(["CRANE"]))
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    assert policy.choose(boards, [], ALLOWED, remaining=9) == "CRANE"
    assert policy.fallback_count == 0


def test_reprompts_on_invalid_then_accepts():
    policy = LLMPolicy(MockProvider(["ZZZZZ", "CRANE"]))
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    assert policy.choose(boards, [], ALLOWED, remaining=9) == "CRANE"
    assert policy.fallback_count == 0


def test_falls_back_after_exhausting_retries():
    policy = LLMPolicy(MockProvider(["ZZZZZ"]), max_retries=2)
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    guess = policy.choose(boards, [], ALLOWED, remaining=9)
    assert guess == "CRANE"  # deterministic min of candidates
    assert policy.fallback_count == 1


def test_render_prompt_shows_feedback_and_candidates():
    boards = [Board(frozenset({"CRANE", "GRAPE"}))]
    history = [TurnFeedback("SLATE", [(X, Y, Y, X, Y)])]
    text = render_prompt(boards, history, Assist.CANDIDATES, remaining=8)
    assert "SLATE" in text
    assert "Board 1" in text
    assert "CRANE" in text  # candidate list included (set is small)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quordle.llm_policy'`.

- [ ] **Step 3: Implement `LLMPolicy`**

`src/quordle/llm_policy.py`:
```python
"""LLMPolicy: an LLM plays Quordle behind the Policy interface (ADR 17)."""

from enum import Enum

from quordle.board import Board
from quordle.engine import TurnFeedback
from quordle.provider import LLMProvider
from quordle.scoring import Mark, Pattern

CANDIDATE_THRESHOLD = 20


class Assist(Enum):
    NONE = "none"
    CONSTRAINTS = "constraints"
    CANDIDATES = "candidates"


def _colors(pattern: Pattern) -> str:
    return "".join(mark.value for mark in pattern)


def _board_constraints(
    board_index: int, history: list[TurnFeedback]
) -> tuple[dict[int, str], set[str], set[str]]:
    greens: dict[int, str] = {}
    present: set[str] = set()
    absent: set[str] = set()
    for turn in history:
        pattern = turn.patterns[board_index]
        if pattern is None:
            continue
        for i, mark in enumerate(pattern):
            ch = turn.guess[i]
            if mark is Mark.GREEN:
                greens[i] = ch
                present.add(ch)
            elif mark is Mark.YELLOW:
                present.add(ch)
            else:
                absent.add(ch)
    absent -= present
    return greens, present, absent


def render_prompt(
    boards: list[Board], history: list[TurnFeedback], assist: Assist, remaining: int
) -> str:
    parts = [
        "You are playing Quordle: four hidden 5-letter words solved at once.",
        "Each guess is scored against all four boards. Per-board feedback:",
        "  G = right letter, right position",
        "  Y = right letter, wrong position",
        "  . = letter not in that board's word",
        f"You have made {len(history)} guesses; {remaining} remain.",
        "",
    ]
    for i, board in enumerate(boards):
        solved = not board.candidates
        parts.append(f"Board {i + 1}" + (" (SOLVED)" if solved else ""))
        lines = [
            f"  {turn.guess}  {_colors(turn.patterns[i])}"
            for turn in history
            if turn.patterns[i] is not None
        ]
        parts.extend(lines or ["  (no guesses yet)"])
        if not solved and assist in (Assist.CONSTRAINTS, Assist.CANDIDATES):
            greens, present, absent = _board_constraints(i, history)
            green_str = ", ".join(f"pos{p + 1}={c}" for p, c in sorted(greens.items())) or "none"
            parts.append(f"  known greens: {green_str}")
            parts.append(f"  must include: {', '.join(sorted(present)) or 'none'}")
            parts.append(f"  excluded: {', '.join(sorted(absent)) or 'none'}")
        if not solved and assist is Assist.CANDIDATES and len(board.candidates) <= CANDIDATE_THRESHOLD:
            parts.append(f"  remaining candidates: {', '.join(sorted(board.candidates))}")
        parts.append("")
    parts.append("Choose the single best next guess: a valid 5-letter word.")
    return "\n".join(parts)


class LLMPolicy:
    def __init__(
        self, provider: LLMProvider, *, assist: Assist = Assist.NONE, max_retries: int = 2
    ) -> None:
        self.provider = provider
        self.assist = assist
        self.max_retries = max_retries
        self.fallback_count = 0

    def choose(
        self,
        boards: list[Board],
        history: list[TurnFeedback],
        allowed: frozenset[str],
        remaining: int,
    ) -> str:
        prompt = render_prompt(boards, history, self.assist, remaining)
        note = ""
        for _ in range(self.max_retries + 1):
            response = self.provider.next_guess(prompt + note)
            guess = response.guess.strip().upper()
            if len(guess) == 5 and guess in allowed:
                return guess
            note = (
                f"\n\nYour previous answer {guess!r} is not a valid guess. "
                "Reply with a valid 5-letter word."
            )
        self.fallback_count += 1
        return self._fallback(boards, allowed)

    def _fallback(self, boards: list[Board], allowed: frozenset[str]) -> str:
        actives = [board.candidates for board in boards if board.candidates]
        pool = sorted(set().union(*actives)) if actives else sorted(allowed)
        return pool[0]
```

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_llm_policy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/llm_policy.py tests/test_llm_policy.py
git commit -m "feat: add LLMPolicy with prompt rendering, reprompt, and fallback"
```

---

### Task 11: Wire the Claude player into the runner CLI

**Files:**
- Modify: `src/quordle/runner.py` (extend `main`)
- Modify: `tests/test_runner.py` (add a CLI-builder test using MockProvider)

**Interfaces:**
- Consumes: `quordle.llm_policy.LLMPolicy`/`Assist`, `quordle.provider.ClaudeProvider`.
- Produces: `build_policy_factory(player: str, assist: str, model: str) -> tuple[Callable[[], Policy], dict]` — returns a policy factory and the metadata to attach. `main` gains `--player {heuristic,claude}`, `--assist {none,constraints,candidates}`, `--model` (default `claude-opus-5`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_runner.py`:
```python
def test_build_policy_factory_heuristic():
    from quordle.runner import build_policy_factory

    factory, metadata = build_policy_factory("heuristic", "none", "claude-opus-5")
    policy = factory()
    assert metadata["player"] == "heuristic"
    assert hasattr(policy, "choose")


def test_build_policy_factory_claude_metadata():
    from quordle.runner import build_policy_factory

    _factory, metadata = build_policy_factory("claude", "constraints", "claude-opus-5")
    assert metadata == {"player": "claude", "model": "claude-opus-5", "assist": "constraints", "mode": "claude"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runner.py -k build_policy_factory -v`
Expected: FAIL — `ImportError: cannot import name 'build_policy_factory'`.

- [ ] **Step 3: Extend the runner**

In `src/quordle/runner.py`, add imports and the builder, and rewrite `main`:
```python
from quordle.llm_policy import Assist, LLMPolicy
from quordle.provider import ClaudeProvider


def build_policy_factory(
    player: str, assist: str, model: str
) -> tuple[Callable[[], Policy], dict]:
    if player == "heuristic":
        return FixedOpenersThenGreedy, {"player": "heuristic"}
    if player == "claude":
        assist_level = Assist(assist)

        def factory() -> Policy:
            return LLMPolicy(ClaudeProvider(model=model), assist=assist_level)

        return factory, {"player": "claude", "model": model, "assist": assist, "mode": "claude"}
    raise ValueError(f"unknown player: {player!r}")
```

Replace `main` with:
```python
def main() -> None:
    parser = argparse.ArgumentParser(description="Play Quordle games and log them.")
    parser.add_argument("-n", "--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=DEFAULT_LOG)
    parser.add_argument("--date", default="2026-08-01")
    parser.add_argument("--player", choices=["heuristic", "claude"], default="heuristic")
    parser.add_argument("--assist", choices=["none", "constraints", "candidates"], default="none")
    parser.add_argument("--model", default="claude-opus-5")
    args = parser.parse_args()

    factory, metadata = build_policy_factory(args.player, args.assist, args.model)
    records = run_many(
        args.count,
        seed=args.seed,
        policy_factory=factory,
        answers=wordlist.load_answers(),
        allowed=wordlist.load_allowed(),
        start_seq=next_seq(args.out),
        date=args.date,
        metadata=metadata,
    )
    append_jsonl(args.out, records)
    print(f"Appended {len(records)} {args.player} games to {args.out}")
```

- [ ] **Step 4: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest tests/test_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/quordle/runner.py tests/test_runner.py
git commit -m "feat: add --player claude to the runner CLI"
```

---

### Task 12: Fold the dashboard into the package

**Files:**
- Create: `src/quordle/dashboard.py` (moved from `quordle_stats.py`, logic unchanged)
- Delete: `quordle_stats.py`
- Create: `tests/test_dashboard.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the JSONL records the runner produces.
- Produces: `load`, `summary`, `build_html`, `main` (console script `quordle-stats`) — behavior unchanged from `quordle_stats.py`.

- [ ] **Step 1: Move the module**

Run: `git mv quordle_stats.py src/quordle/dashboard.py`

- [ ] **Step 2: Write the failing test**

`tests/test_dashboard.py`:
```python
from quordle.dashboard import summary


def test_summary_counts_wins_and_boards():
    games = [
        {
            "seq": 1, "won": True, "totalGuessesUsed": 6, "boardsSolved": 4, "maxGuesses": 9,
            "words": [{"board": b, "answer": "CRANE", "solvedOnGuess": 3} for b in range(1, 5)],
        }
    ]
    stats = summary(games)
    assert stats["games"] == 1
    assert stats["win_rate"] == "100%"
    assert stats["board_rate"] == "100%"
```

- [ ] **Step 3: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_dashboard.py -v`
Expected: PASS once the module resolves at `quordle.dashboard` (the move already provides the code). If it FAILs with `ModuleNotFoundError`, confirm the `git mv` placed the file at `src/quordle/dashboard.py`.

- [ ] **Step 4: Update the README**

In `README.md`, replace the `## Usage` fenced block with:
```bash
pip install -e ".[dev]"
quordle-sim -n 100 --seed 0                       # heuristic games -> data/quordle_games.jsonl
quordle-sim --player claude -n 5 --assist none    # Claude-played games (needs API access)
quordle-stats                                     # build quordle_dashboard.html
```
Update the "What's here" tree to show `src/quordle/` (`wordlist`, `scoring`, `board`, `engine`, `policy`, `solver`, `provider`, `llm_policy`, `runner`, `dashboard`) instead of the top-level `quordle_stats.py`.

- [ ] **Step 5: Run the gate**

Run: `ruff format --check . && ruff check . && mypy && python -m pytest -v`
Expected: PASS (full suite).

- [ ] **Step 6: Commit**

```bash
git add src/quordle/dashboard.py tests/test_dashboard.py README.md
git commit -m "refactor: move dashboard into the quordle package"
```

---

### Task 13: Generate games (heuristic bulk + Claude batch) and verify

**Files:**
- No committed source changes (log and dashboard are gitignored). Operational verification.

**Interfaces:**
- Consumes: the `quordle-sim` and `quordle-stats` console scripts.
- Produces: `data/quordle_games.jsonl` with 100+ games (including a small Claude batch) and a regenerated `quordle_dashboard.html`.

- [ ] **Step 1: Generate the heuristic bulk to reach 100+**

Run:
```bash
wc -l data/quordle_games.jsonl 2>/dev/null || echo 0
quordle-sim -n 100 --seed 0 --date 2026-08-01
wc -l data/quordle_games.jsonl
```
Expected: the log has ≥ 100 lines; `seq` continues from the existing log.

- [ ] **Step 2: Confirm Claude API access, then play a small Claude batch**

Check credentials first (do not print secrets):
```bash
ant auth status 2>/dev/null || echo "no ant profile; set ANTHROPIC_API_KEY"
```
If credentials are available, play a small opt-in batch (5 games — LLM play is slow and costs money; keep it small and confirm with the user before scaling up):
```bash
quordle-sim --player claude -n 5 --assist none --seed 100 --date 2026-08-01
```
Expected: `Appended 5 claude games to data/quordle_games.jsonl`. If no credentials, skip this step and note it in the report.

- [ ] **Step 3: Build the dashboard**

Run: `quordle-stats`
Expected: `Wrote quordle_dashboard.html (<N> games, win rate <p>%)` with N ≥ 100.

- [ ] **Step 4: Sanity-check the output**

Run:
```bash
python -c "import json;g=[json.loads(l) for l in open('data/quordle_games.jsonl') if l.strip()];print('games',len(g));print('wins',sum(x['won'] for x in g));print('claude games',sum(1 for x in g if x.get('player')=='claude'));print('fallbacks',sum(x.get('fallbacks',0) for x in g))"
```
Expected: sensible numbers — a high (not necessarily perfect) heuristic win rate; the Claude games present if Step 2 ran; low fallback counts. If the heuristic win rate is implausibly low (< 50%), stop and investigate before declaring Phase 1 done.

- [ ] **Step 5: Open the dashboard and eyeball the charts**

Open `quordle_dashboard.html` in a browser; confirm all six charts render and the stat tiles match Step 4.

- [ ] **Step 6: (No commit — outputs are gitignored.)** Report the summary numbers, including how Claude played, for review.

---

## Self-Review

**Spec coverage:**
- Engine seam (`Environment`/`submit`) → Task 5. ✅
- Feedback history to policies (`TurnFeedback`) → Tasks 5, 7. ✅
- Scoring with duplicates → Task 3. ✅
- Board filtering → Task 4. ✅
- Heuristic baseline (openers → greedy) → Task 6. ✅
- Answer-blind solver → Task 7. ✅
- Runner + JSONL schema → Task 8; Claude wiring → Task 11; 100 games + Claude batch → Task 13. ✅
- Word lists bundled → Task 2. ✅
- src layout + toolchain + CI (ADRs 9, 10) → Task 1. ✅
- LLM players (ADR 17): provider abstraction → Task 9; `LLMPolicy` + assist knob + reprompt/fallback → Task 10; Claude via `anthropic` + structured outputs, mock keeps CI offline → Tasks 9, 10, 11. ✅
- Dashboard reuse (ADR 16) → Task 12. ✅
- Gemini + objective/comparison harness → **Phase 2, out of scope** (the `LLMProvider` and `Policy` seams are in place). ✅

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" — each task has concrete code and tests. ✅

**Type consistency:** `Board.candidates: frozenset[str]`; `Pattern`/`Mark` from scoring; `TurnFeedback(guess, patterns)` produced by the solver (Task 7) and consumed by both policies (Tasks 6, 10); `Policy.choose(boards, history, allowed, remaining)` identical across Tasks 6, 7, 10, and the test doubles; `GuessResponse(reasoning, guess)` and `LLMProvider.next_guess` consistent across Tasks 9–11; `run_game(..., metadata)`, `run_many(..., policy_factory)`, and `build_policy_factory` consistent across Tasks 8, 11, 13; `fallback_count` set in Task 10 and read in Task 8. ✅
