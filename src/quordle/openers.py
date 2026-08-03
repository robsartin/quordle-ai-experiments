"""Precomputed fixed opening guesses (design doc 2026-08-02-fixed-openers).

Scoring a set of openers over the 2315 possible answers: playing them
partitions the answers by their joint feedback signature -- a smaller
average partition means more information extracted before any
answer-specific guessing begins.
"""

import sys
from collections import Counter
from collections.abc import Iterable, Sequence

from quordle import wordlist
from quordle.scoring import Pattern, score


def signature(openers: Sequence[str], answer: str) -> tuple[Pattern, ...]:
    """The per-opener feedback `answer` would produce against each opener,
    in order -- the joint signature that determines which bucket `answer`
    falls into for this set of openers."""
    return tuple(score(opener, answer) for opener in openers)


def expected_remaining(openers: Sequence[str], answers: Sequence[str]) -> float:
    """Mean, over `answers`, of the size of the answer's signature bucket
    (lower is better -- 1.0 is the theoretical minimum: every answer in its
    own bucket)."""
    buckets: Counter[tuple[Pattern, ...]] = Counter(signature(openers, a) for a in answers)
    return sum(count * count for count in buckets.values()) / len(answers)


def best_openers(answers: Sequence[str], pool: Iterable[str], k: int) -> list[str]:
    """Greedily build a k-tuple of openers: pick the single word minimizing
    `expected_remaining`, then the word that best complements it, repeating
    to `k`. Brute-forcing the optimal k-tuple is infeasible, so this is a
    greedy approximation. Ties break alphabetically (deterministic)."""
    ordered = sorted(set(pool))
    chosen: list[str] = []
    chosen_set: set[str] = set()
    for _ in range(k):
        candidates = [w for w in ordered if w not in chosen_set]
        best = min(candidates, key=lambda w: expected_remaining((*chosen, w), answers))
        chosen.append(best)
        chosen_set.add(best)
    return chosen


# Greedy top-3 over the full bundled lists (pool = load_allowed(), 12,972
# words; scored over load_answers(), 2315 answers) -- computed once via
# `python -m quordle.openers 3` and hardcoded here so no run pays that
# ~6-minute cost. expected_remaining after each: ROATE 60.42, +LINDS 5.12,
# +CHUMP 1.64 (theoretical minimum is 1.0 -- every answer in its own
# bucket).
OPENERS: tuple[str, ...] = ("ROATE", "LINDS", "CHUMP")


def _format_report(openers: list[str], answers: Sequence[str]) -> str:
    lines = []
    for i in range(1, len(openers) + 1):
        prefix = openers[:i]
        er = expected_remaining(prefix, answers)
        lines.append(f"{i}: {' '.join(prefix)}  expected_remaining={er:.4f}")
    return "\n".join(lines)


def main() -> None:
    """`python -m quordle.openers [k]` -- prints the greedy top-k openers
    (and their expected_remaining) over the bundled lists: pool =
    load_allowed() (12,972 words), scored over load_answers() (2315
    answers). Several minutes for k=3 over the full allowed pool (~90M
    `score` calls; measured ~6 minutes on one dev machine)."""
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    answers = wordlist.load_answers()
    pool = wordlist.load_allowed()
    openers = best_openers(answers, pool, k)
    print(_format_report(openers, answers))


if __name__ == "__main__":  # pragma: no cover -- exercised by running the script, not by tests
    main()
