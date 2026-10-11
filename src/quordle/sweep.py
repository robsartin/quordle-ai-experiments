"""Top-up sweep (issue #39): keep playing until N games have *completed*.

Free-tier Gemini throttles (429/503/504), so a fixed `-n N` sweep logs fewer than
N games. This module is the pure, injectable core of the fix; it knows nothing
about providers, files or clocks -- those arrive as callables so tests run
instantly and offline.

"Completed" means a game that ran to a scored result (won or lost) and was logged.
A throttled or otherwise errored attempt produces no record and never counts.
"""


def backoff_delay(consecutive_throttles: int, *, base: float, cap: float) -> float:
    """Seconds to wait after `consecutive_throttles` throttled attempts in a row:
    `base`, doubling each time, never above `cap`; 0 when nothing is throttled."""
    if consecutive_throttles <= 0:
        return 0.0
    return min(cap, base * 2 ** (consecutive_throttles - 1))
