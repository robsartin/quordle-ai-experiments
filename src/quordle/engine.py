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
    def __init__(self, answers: list[str], allowed: frozenset[str], max_guesses: int = 9) -> None:
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
