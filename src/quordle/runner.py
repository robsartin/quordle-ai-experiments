"""Play games and append them to the JSONL log (ADR 16)."""

import argparse
import json
import random
from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol

from quordle import wordlist
from quordle.board import Board
from quordle.engine import Environment, SimEngine, TurnFeedback
from quordle.llm_policy import Assist, LLMPolicy
from quordle.policy import FixedOpenersThenGreedy, Policy
from quordle.provider import ClaudeProvider
from quordle.solver import SolveResult, solve

if TYPE_CHECKING:
    from quordle.browser.browser_env import GuessRejected

DEFAULT_LOG = "data/quordle_games.jsonl"


class _ContextEnv(Environment, Protocol):
    """An Environment that's also its own context manager, like BrowserEnv.

    `run_browser_game`'s injectable `env_factory` must return one of these
    (not a bare Environment) so it can still be used as `with env_factory()
    as env: ...` -- required for real browser cleanup, and satisfiable by a
    trivial no-op `__enter__`/`__exit__` on a test double.
    """

    def __enter__(self) -> "_ContextEnv": ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


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


def _play_browser_game(
    env: Environment, policy: Policy, answers: tuple[str, ...]
) -> tuple[SolveResult, "GuessRejected | None"]:
    """Mirror solver.solve()'s loop, but recover from the live site rejecting
    a guess mid-game instead of losing all progress made so far.

    solve() is deliberately environment-agnostic -- it must not import a
    browser-specific exception type -- and its guesses/solved_on state is
    local to its call frame, so it has no way to expose partial progress if
    env.submit() raises. A site-side rejection is unique to BrowserEnv
    (SimEngine can never raise it), so this loop, otherwise identical to
    solve()'s, lives here instead: on GuessRejected it returns whatever
    guesses/solved_on were recorded before the rejection, so the caller can
    still log a (partial, won=False) record instead of losing the game --
    and, for a real `--player claude` run, the API spend that produced those
    accepted guesses.
    """
    from quordle.browser.browser_env import GuessRejected

    full = frozenset(w.upper() for w in answers)
    boards = [Board(full) for _ in range(env.num_boards)]
    guesses: list[str] = []
    history: list[TurnFeedback] = []
    solved_on: list[int | None] = [None] * env.num_boards

    while not env.finished():
        guess = policy.choose(boards, history, env.allowed, env.remaining_guesses())
        try:
            result = env.submit(guess)
        except GuessRejected as exc:
            return SolveResult(guesses, solved_on), exc
        guesses.append(guess)
        history.append(TurnFeedback(guess, [state.pattern for state in result.boards]))
        for i, state in enumerate(result.boards):
            if state.solved:
                if solved_on[i] is None:
                    solved_on[i] = state.solved_on
                boards[i] = Board(frozenset())
            elif state.pattern is not None:
                boards[i] = boards[i].filter(guess, state.pattern)
        # Per-guess progress so unattended browser runs show they are alive
        # (a stalled turn is otherwise silent). Browser-only -- sim runs, which
        # loop over many games, stay quiet via their own summary line.
        solved_count = sum(1 for s in solved_on if s is not None)
        print(
            f"  guess {len(guesses)}/{env.max_guesses}: {guess} -> "
            f"{solved_count}/{env.num_boards} boards solved",
            flush=True,
        )

    return SolveResult(guesses, solved_on), None


def run_browser_game(
    policy: Policy,
    *,
    seq: int,
    date: str,
    allowed: frozenset[str],
    headless: bool,
    metadata: dict[str, str] | None = None,
    env_factory: Callable[[], _ContextEnv] | None = None,
) -> dict[str, Any]:
    factory = env_factory
    if factory is None:

        def _default_env_factory() -> _ContextEnv:
            from quordle.browser.browser_env import BrowserEnv

            return BrowserEnv(allowed=allowed, headless=headless)

        factory = _default_env_factory

    with factory() as env:
        result, rejected = _play_browser_game(env, policy, wordlist.load_answers())

    if rejected is not None:
        print(
            f"Browser game ended early after {len(result.guesses)} guess(es) -- "
            f"the site rejected a guess: {rejected}. Logging the partial result."
        )

    words = [
        {"board": i + 1, "answer": "", "solvedOnGuess": result.solved_on[i] or 0}
        for i in range(len(result.solved_on))
    ]
    boards_solved = sum(1 for w in words if w["solvedOnGuess"])
    record: dict[str, Any] = {
        "seq": seq,
        "date": date,
        "mode": "browser",
        "guesses": result.guesses,
        "totalGuessesUsed": len(result.guesses),
        "maxGuesses": 9,
        "boardsSolved": boards_solved,
        "won": boards_solved == len(words),
        "words": words,
    }
    if rejected is not None:
        record["endedEarly"] = True
    fallbacks = getattr(policy, "fallback_count", 0)
    if fallbacks:
        record["fallbacks"] = fallbacks
    if metadata:
        record.update(metadata)
    return record


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Play Quordle games and log them.")
    parser.add_argument("-n", "--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=DEFAULT_LOG)
    parser.add_argument("--date", default="2026-08-01")
    parser.add_argument("--player", choices=["heuristic", "claude"], default="heuristic")
    parser.add_argument("--assist", choices=["none", "constraints", "candidates"], default="none")
    parser.add_argument("--model", default="claude-opus-5")
    parser.add_argument("--env", choices=["sim", "browser"], default="sim")
    parser.add_argument("--headed", action="store_true")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    factory, metadata = build_policy_factory(args.player, args.assist, args.model)

    if args.env == "browser":
        record = run_browser_game(
            factory(),
            seq=next_seq(args.out),
            date=args.date,
            allowed=wordlist.load_allowed(),
            headless=not args.headed,
            metadata={**metadata, "mode": "browser"},
        )
        append_jsonl(args.out, [record])
        print(f"Appended 1 {args.player} browser game to {args.out}")
        return

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
