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
