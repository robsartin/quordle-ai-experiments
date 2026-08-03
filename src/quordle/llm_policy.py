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
            f"  {turn.guess}  {_colors(pattern)}"
            for turn in history
            if (pattern := turn.patterns[i]) is not None
        ]
        parts.extend(lines or ["  (no guesses yet)"])
        if not solved and assist in (Assist.CONSTRAINTS, Assist.CANDIDATES):
            greens, present, absent = _board_constraints(i, history)
            green_str = ", ".join(f"pos{p + 1}={c}" for p, c in sorted(greens.items())) or "none"
            parts.append(f"  known greens: {green_str}")
            parts.append(f"  must include: {', '.join(sorted(present)) or 'none'}")
            parts.append(f"  excluded: {', '.join(sorted(absent)) or 'none'}")
        if (
            not solved
            and assist is Assist.CANDIDATES
            and len(board.candidates) <= CANDIDATE_THRESHOLD
        ):
            parts.append(f"  remaining candidates: {', '.join(sorted(board.candidates))}")
        parts.append("")
    parts.append("Choose the single best next guess: a valid 5-letter word.")
    return "\n".join(parts)


class LLMPolicy:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        assist: Assist = Assist.NONE,
        max_retries: int = 2,
        openers: tuple[str, ...] = (),
    ) -> None:
        self.provider = provider
        self.assist = assist
        self.max_retries = max_retries
        self.openers = openers
        self.fallback_count = 0

    def choose(
        self,
        boards: list[Board],
        history: list[TurnFeedback],
        allowed: frozenset[str],
        remaining: int,
        excluded: frozenset[str] = frozenset(),
    ) -> str:
        if len(history) < len(self.openers):
            return self.openers[len(history)]
        prompt = render_prompt(boards, history, self.assist, remaining)
        if excluded:
            prompt += (
                "\n\nThe live site refused these words; do NOT guess them again: "
                + ", ".join(sorted(excluded))
                + ". Choose a different valid 5-letter word."
            )
        note = ""
        for _ in range(self.max_retries + 1):
            response = self.provider.next_guess(prompt + note)
            guess = response.guess.strip().upper()
            if len(guess) == 5 and guess in allowed and guess not in excluded:
                return guess
            note = (
                f"\n\nYour previous answer {guess!r} is not a valid guess. "
                "Reply with a valid 5-letter word."
            )
        self.fallback_count += 1
        return self._fallback(boards, allowed, excluded)

    def _fallback(
        self, boards: list[Board], allowed: frozenset[str], excluded: frozenset[str] = frozenset()
    ) -> str:
        actives = [board.candidates for board in boards if board.candidates]
        pool = sorted(set().union(*actives)) if actives else sorted(allowed)
        pool = [p for p in pool if p not in excluded]
        if not pool:
            pool = sorted(allowed - excluded)
        if not pool:
            pool = sorted(allowed)
        return pool[0]
