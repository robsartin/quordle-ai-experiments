"""Top-up sweep (issue #39): keep playing until N games have *completed*.

Free-tier Gemini throttles (429/503/504), so a fixed `-n N` sweep logs fewer than
N games. This module is the pure, injectable core of the fix; it knows nothing
about providers, files or clocks -- those arrive as callables so tests run
instantly and offline.

"Completed" means a game that ran to a scored result (won or lost) and was logged.
A throttled or otherwise errored attempt produces no record and never counts.
"""

import json
import random
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

# The record fields that identify an experiment config. Two logged games belong to
# the same sweep only if every one of these agrees ("mode" keeps sim and browser
# apart: a browser game is a different puzzle source and is never topped up here).
CONFIG_KEYS = ("player", "model", "assist", "mode", "openers")

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


def completed_puzzles(path: str, config: dict[str, Any]) -> list[tuple[str, ...]]:
    """Puzzle keys of every *completed* game in the log for this config.

    Completed = logged for this exact config and not `endedEarly` (a game cut short
    by a stall or a rejected guess has no full score). A lost game is still
    completed: it ran to a scored result. A missing log is simply empty; a
    malformed line raises rather than being silently dropped, because an
    undercount would make the sweep over-play.
    """
    try:
        fh = open(path, encoding="utf-8")
    except FileNotFoundError:
        return []
    keys = [k for k in CONFIG_KEYS if k in config]
    puzzles: list[tuple[str, ...]] = []
    with fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("endedEarly"):
                continue
            if any(record.get(k) != config[k] for k in keys):
                continue
            puzzles.append(puzzle_key(w["answer"] for w in record["words"]))
    return puzzles


@dataclass(frozen=True)
class SweepResult:
    """What a top-up run did. `completed` counts only games added this run."""

    completed: int
    attempts: int
    throttled: int
    reached_target: bool


def sweep_until_completed(
    target: int,
    *,
    already_completed: int,
    puzzles: Iterator[list[str]],
    play: Callable[[list[str], int], dict[str, Any]],
    on_record: Callable[[dict[str, Any]], None],
    is_transient: Callable[[Exception], bool],
    max_attempts: int,
    sleep: Callable[[float], None],
    backoff_base: float,
    backoff_cap: float,
    start_seq: int = 1,
    log: Callable[[str], None] = print,
) -> SweepResult:
    """Play fresh puzzles until the config holds `target` completed games.

    `play(picks, seq)` returns a scored record or raises. A transient (throttle)
    error means the attempt produced no result: it is not counted toward the
    target, the next attempt takes a *new* puzzle, and the sweep backs off. Any
    other exception is a real bug and propagates (records already handed to
    `on_record` are kept). `max_attempts` bounds total attempts so a persistent
    outage ends the sweep instead of spinning.
    """
    completed = attempts = throttled = 0
    while already_completed + completed < target and attempts < max_attempts:
        picks = next(puzzles, None)
        if picks is None:
            log("Puzzle pool exhausted; stopping.")
            break
        seq = start_seq + attempts
        attempts += 1
        try:
            record = play(picks, seq)
        except Exception as exc:
            if not is_transient(exc):
                raise
            throttled += 1
            log(f"Attempt {attempts} throttled ({exc!r}); not counted, moving to a fresh puzzle.")
            continue
        on_record(record)
        completed += 1
    return SweepResult(
        completed=completed,
        attempts=attempts,
        throttled=throttled,
        reached_target=already_completed + completed >= target,
    )
