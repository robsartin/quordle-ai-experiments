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
