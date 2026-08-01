"""Play games and append them to the JSONL log (ADR 16)."""

import argparse
import json
import random
from collections.abc import Callable
from typing import Any

from quordle import wordlist
from quordle.engine import SimEngine
from quordle.llm_policy import Assist, LLMPolicy
from quordle.policy import FixedOpenersThenGreedy, Policy
from quordle.provider import ClaudeProvider
from quordle.solver import solve

DEFAULT_LOG = "data/quordle_games.jsonl"


def sample_answers(rng: random.Random, answers: tuple[str, ...], count: int = 4) -> list[str]:
    return rng.sample(list(answers), count)


def run_game(
    answers: list[str],
    policy: Policy,
    *,
    seq: int,
    date: str,
    allowed: frozenset[str],
    max_guesses: int = 9,
    mode: str = "sim",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    answers = [a.upper() for a in answers]
    engine = SimEngine(answers, allowed, max_guesses=max_guesses)
    result = solve(engine, policy, wordlist.load_answers())
    words = [
        {"board": i + 1, "answer": answers[i], "solvedOnGuess": result.solved_on[i] or 0}
        for i in range(len(answers))
    ]
    boards_solved = sum(1 for w in words if w["solvedOnGuess"])
    record: dict[str, Any] = {
        "seq": seq,
        "date": date,
        "mode": mode,
        "guesses": result.guesses,
        "totalGuessesUsed": len(result.guesses),
        "maxGuesses": max_guesses,
        "boardsSolved": boards_solved,
        "won": boards_solved == len(answers),
        "words": words,
    }
    fallbacks = getattr(policy, "fallback_count", 0)
    if fallbacks:
        record["fallbacks"] = fallbacks
    if metadata:
        record.update(metadata)
    return record


def run_many(
    count: int,
    *,
    seed: int,
    policy_factory: Callable[[], Policy],
    answers: tuple[str, ...],
    allowed: frozenset[str],
    start_seq: int,
    date: str,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for offset in range(count):
        picks = sample_answers(rng, answers, count=4)
        records.append(
            run_game(
                picks,
                policy_factory(),
                seq=start_seq + offset,
                date=date,
                allowed=allowed,
                metadata=metadata,
            )
        )
    return records


def append_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def next_seq(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            seqs = [json.loads(line)["seq"] for line in fh if line.strip()]
        return max(seqs, default=0) + 1
    except FileNotFoundError:
        return 1


def build_policy_factory(
    player: str, assist: str, model: str
) -> tuple[Callable[[], Policy], dict[str, str]]:
    if player == "heuristic":
        return FixedOpenersThenGreedy, {"player": "heuristic"}
    if player == "claude":
        assist_level = Assist(assist)

        def factory() -> Policy:
            return LLMPolicy(ClaudeProvider(model=model), assist=assist_level)

        return factory, {"player": "claude", "model": model, "assist": assist, "mode": "claude"}
    raise ValueError(f"unknown player: {player!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play Quordle games and log them.")
    parser.add_argument("-n", "--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=DEFAULT_LOG)
    parser.add_argument("--date", default="2026-08-01")
    parser.add_argument("--player", choices=["heuristic", "claude"], default="heuristic")
    parser.add_argument("--assist", choices=["none", "constraints", "candidates"], default="none")
    parser.add_argument("--model", default="claude-opus-5")
    args = parser.parse_args()

    factory, metadata = build_policy_factory(args.player, args.assist, args.model)
    records = run_many(
        args.count,
        seed=args.seed,
        policy_factory=factory,
        answers=wordlist.load_answers(),
        allowed=wordlist.load_allowed(),
        start_seq=next_seq(args.out),
        date=args.date,
        metadata=metadata,
    )
    append_jsonl(args.out, records)
    print(f"Appended {len(records)} {args.player} games to {args.out}")


if __name__ == "__main__":
    main()
