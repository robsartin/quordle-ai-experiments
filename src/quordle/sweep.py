"""Top-up sweep (issue #39): keep playing until N games have *completed*.

Free-tier Gemini throttles (429/503/504), so a fixed `-n N` sweep logs fewer than
N games. This module is the pure, injectable core of the fix; it knows nothing
about providers, files or clocks -- those arrive as callables so tests run
instantly and offline.

"Completed" means a game that ran to a scored result (won or lost) and was logged.
A throttled or otherwise errored attempt produces no record and never counts.
"""

import random
from collections.abc import Iterable, Iterator

_MAX_CONSECUTIVE_DUPLICATES = 1000


def puzzle_key(answers: Iterable[str]) -> tuple[str, ...]:
    """Identity of a puzzle: its four answers, order- and case-insensitive."""
    return tuple(sorted(a.upper() for a in answers))


def puzzle_stream(
    seed: int,
    answers: tuple[str, ...],
    *,
    done: Iterable[Iterable[str]],
    count: int = 4,
) -> Iterator[list[str]]:
    """Endless-in-practice stream of fresh puzzles from `Random(seed)`.

    Puzzles whose key is in `done` (already completed in the log) or already
    yielded by this stream are skipped, so a topped-up game is always a new puzzle
    -- never a replay that would pollute a paired comparison. Ends only if the pool
    is exhausted (a long unbroken run of duplicates), which a real word list never
    reaches.
    """
    rng = random.Random(seed)
    seen = {puzzle_key(d) for d in done}
    duplicates = 0
    while duplicates < _MAX_CONSECUTIVE_DUPLICATES:
        picks = rng.sample(list(answers), count)
        key = puzzle_key(picks)
        if key in seen:
            duplicates += 1
            continue
        duplicates = 0
        seen.add(key)
        yield picks


def backoff_delay(consecutive_throttles: int, *, base: float, cap: float) -> float:
    """Seconds to wait after `consecutive_throttles` throttled attempts in a row:
    `base`, doubling each time, never above `cap`; 0 when nothing is throttled."""
    if consecutive_throttles <= 0:
        return 0.0
    return float(min(cap, base * 2 ** (consecutive_throttles - 1)))
