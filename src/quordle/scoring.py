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
