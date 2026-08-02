"""A single Quordle board: the answers still consistent with feedback."""

from dataclasses import dataclass

from quordle.scoring import Pattern, score


@dataclass(frozen=True)
class Board:
    candidates: frozenset[str]

    def filter(self, guess: str, pattern: Pattern) -> "Board":
        guess = guess.upper()
        return Board(frozenset(c for c in self.candidates if score(guess, c) == pattern))
