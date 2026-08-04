"""Play games and append them to the JSONL log (ADR 16)."""

import argparse
import json
import os
import random
import shutil
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol

from quordle import wordlist
from quordle.board import Board
from quordle.engine import Environment, SimEngine, TurnFeedback
from quordle.gemini_provider import GeminiProvider
from quordle.llm_policy import Assist, LLMPolicy
from quordle.openers import OPENERS
from quordle.policy import FixedOpenersThenGreedy, Policy
from quordle.provider import ClaudeProvider, NoStructuredOutput
from quordle.solver import SolveResult, solve

DEFAULT_LOG = "data/quordle_games.jsonl"
MAX_REJECT_RETRIES = 3


def _transient_error_types() -> tuple[type[BaseException], ...]:
    """Per-call failures a multi-game sweep should skip (not crash on): a
    provider connection/timeout stall and no-structured-output. Auth / 4xx /
    bad-request errors (anthropic.APIStatusError, google.genai ClientError) are
    deliberately NOT included -- those are real bugs that must fail loudly
    rather than silently skip every game. Imported lazily to keep module import
    light, matching the existing per-loop import style."""
    import httpx
    from anthropic import APIConnectionError
    from google.genai import errors as genai_errors

    return (APIConnectionError, NoStructuredOutput, genai_errors.ServerError, httpx.TransportError)


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
    def read_answers(self) -> list[str]: ...


class _MultiGameEnv(_ContextEnv, Protocol):
    """A browser Environment that can also start a fresh game in place."""

    def __enter__(self) -> "_MultiGameEnv": ...
    def new_game(self) -> None: ...


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
    out: str | None = None,
) -> list[dict[str, Any]]:
    """Play `count` sim games and return their records.

    When `out` is given, each game is appended the instant it finishes (issue
    #29) rather than the whole batch at the end -- so a run killed or crashed
    mid-batch keeps every completed game, matching the browser path.

    A game interrupted by a transient API stall (an LLM player -- a real bug or
    an out-of-credits error still propagates loudly) is skipped and the batch
    continues, instead of one stall crashing a multi-hour sweep.
    """
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for offset in range(count):
        picks = sample_answers(rng, answers, count=4)
        seq = start_seq + offset
        try:
            record = run_game(
                picks,
                policy_factory(),
                seq=seq,
                date=date,
                allowed=allowed,
                metadata=metadata,
            )
        except _transient_error_types() as exc:
            print(f"Sim game {seq} interrupted by a transient API error ({exc!r}); skipping.")
            continue
        records.append(record)
        if out is not None:
            append_jsonl(out, [record])
    return records


def append_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    _backup_if_nonempty(path)
    with open(path, "a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")


def _backup_if_nonempty(path: str) -> None:
    """Snapshot an existing non-empty log to ``<path>.bak`` before appending,
    leaving one recovery point. The game log is gitignored and irreplaceable,
    and was once externally truncated to empty (issue #11); a rolling backup
    means a bad append or accidental clobber doesn't lose everything.
    """
    if os.path.exists(path) and os.path.getsize(path) > 0:
        shutil.copy2(path, path + ".bak")


def next_seq(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            seqs = [json.loads(line)["seq"] for line in fh if line.strip()]
        return max(seqs, default=0) + 1
    except FileNotFoundError:
        return 1


def build_policy_factory(
    player: str, assist: str, model: str | None, fixed_openers: int
) -> tuple[Callable[[], Policy], dict[str, Any]]:
    openers = OPENERS[:fixed_openers]
    if player == "heuristic":

        def heuristic_factory() -> Policy:
            return FixedOpenersThenGreedy(list(openers))

        return heuristic_factory, {"player": "heuristic", "openers": fixed_openers}
    if player == "claude":
        assist_level = Assist(assist)
        resolved = model or "claude-sonnet-5"

        def claude_factory() -> Policy:
            return LLMPolicy(ClaudeProvider(model=resolved), assist=assist_level, openers=openers)

        return claude_factory, {
            "player": "claude",
            "model": resolved,
            "assist": assist,
            "mode": "claude",
            "openers": fixed_openers,
        }
    if player == "gemini":
        assist_level = Assist(assist)
        resolved = model or "gemini-2.5-flash"

        def gemini_factory() -> Policy:
            return LLMPolicy(GeminiProvider(model=resolved), assist=assist_level, openers=openers)

        return gemini_factory, {
            "player": "gemini",
            "model": resolved,
            "assist": assist,
            "mode": "gemini",
            "openers": fixed_openers,
        }
    raise ValueError(f"unknown player: {player!r}")


def _play_browser_game(
    env: Environment, policy: Policy, answers: tuple[str, ...]
) -> tuple[SolveResult, "Exception | None"]:
    """Mirror solver.solve()'s loop, but recover from two mid-game failures
    unique to live play instead of losing all progress made so far: the site
    rejecting a guess, and a transient API stall while an LLM policy is
    thinking.

    solve() is deliberately environment-agnostic -- it must not import a
    browser-specific exception type -- and its guesses/solved_on state is
    local to its call frame, so it has no way to expose partial progress if a
    call raises. Both failures are unique to live play (SimEngine/MockProvider
    can never raise them), so this loop, otherwise identical to solve()'s,
    lives here instead.

    A rejected guess (the site refuses a word still in our bundled `allowed`
    set) is retried within the SAME turn with the rejected word(s) excluded,
    up to MAX_REJECT_RETRIES times, so the game continues instead of ending.
    Only if every retry for a turn is also rejected does the game end early.
    On that, or on a transient API stall, this returns whatever
    guesses/solved_on were recorded first, so the caller can still log a
    (partial, won=False) record -- preserving, for a real `--player claude`
    run, the API spend that produced the accepted guesses -- and an
    unattended multi-game loop keeps going to the next game instead of
    crashing.

    Only per-call transient failures are caught: APIConnectionError (covering
    APITimeoutError) and NoStructuredOutput (thinking exhausted max_tokens
    before a guess). Auth/bad-request errors propagate, since those are real
    bugs that should fail loudly rather than silently ending every game.
    """
    from quordle.browser.browser_env import GuessRejected

    full = frozenset(w.upper() for w in answers)
    boards = [Board(full) for _ in range(env.num_boards)]
    guesses: list[str] = []
    history: list[TurnFeedback] = []
    solved_on: list[int | None] = [None] * env.num_boards

    while not env.finished():
        excluded: set[str] = set()
        rejected: GuessRejected | None = None
        for _ in range(MAX_REJECT_RETRIES + 1):
            try:
                guess = policy.choose(
                    boards,
                    history,
                    env.allowed,
                    env.remaining_guesses(),
                    excluded=frozenset(excluded),
                )
            except _transient_error_types() as exc:
                assert isinstance(exc, Exception)  # all caught types are Exception subclasses
                return SolveResult(guesses, solved_on), exc
            try:
                result = env.submit(guess)
            except GuessRejected as exc:
                excluded.add(guess)
                rejected = exc
                continue
            # accepted:
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
            # (a stalled turn is otherwise silent). Browser-only -- sim runs,
            # which loop over many games, stay quiet via their own summary line.
            solved_count = sum(1 for s in solved_on if s is not None)
            print(
                f"  guess {len(guesses)}/{env.max_guesses}: {guess} -> "
                f"{solved_count}/{env.num_boards} boards solved",
                flush=True,
            )
            break
        else:
            return SolveResult(guesses, solved_on), rejected

    return SolveResult(guesses, solved_on), None


def _browser_record(
    result: SolveResult,
    ended_early: "Exception | None",
    *,
    seq: int,
    date: str,
    answers: list[str],
    fallbacks: int,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    words = [
        {
            "board": i + 1,
            "answer": answers[i] if i < len(answers) else "",
            "solvedOnGuess": result.solved_on[i] or 0,
        }
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
    if ended_early is not None:
        record["endedEarly"] = True
    if fallbacks:
        record["fallbacks"] = fallbacks
    if metadata:
        record.update(metadata)
    return record


def run_browser_game(
    policy: Policy,
    *,
    seq: int,
    date: str,
    allowed: frozenset[str],
    headless: bool,
    metadata: dict[str, Any] | None = None,
    env_factory: Callable[[], _MultiGameEnv] | None = None,
) -> dict[str, Any]:
    records = run_browser_games(
        lambda: policy,
        count=1,
        start_seq=seq,
        date=date,
        allowed=allowed,
        headless=headless,
        metadata=metadata,
        env_factory=env_factory,
    )
    return records[0]


def run_browser_games(
    policy_factory: Callable[[], Policy],
    *,
    count: int,
    start_seq: int,
    date: str,
    allowed: frozenset[str],
    headless: bool,
    metadata: dict[str, Any] | None = None,
    env_factory: Callable[[], _MultiGameEnv] | None = None,
    out: str | None = None,
) -> list[dict[str, Any]]:
    """Play `count` practice games in ONE long-lived browser, logging each.

    Between games, new_game() starts a fresh puzzle in the same browser. A
    game that fails unexpectedly is logged-and-skipped so the batch continues;
    if new_game() cannot reach a fresh puzzle (e.g. after an early end -- a
    deferred case), the batch ends gracefully with the games completed so far.
    A fresh policy per game (via policy_factory) keeps per-game state clean.

    When `out` is given, each game is appended to that log the instant it
    finishes (issue #26) rather than the whole batch at the end -- so a run
    that is killed or crashes mid-batch keeps every completed game, the log
    fills in live, and #11's per-append backup runs per game. The full list is
    still returned for callers that want it (tests, the count=1 wrapper).
    """
    factory = env_factory
    if factory is None:

        def _default_env_factory() -> _MultiGameEnv:
            from quordle.browser.browser_env import BrowserEnv

            return BrowserEnv(allowed=allowed, headless=headless)

        factory = _default_env_factory

    records: list[dict[str, Any]] = []
    with factory() as env:
        for offset in range(count):
            seq = start_seq + offset
            if offset > 0:
                try:
                    env.new_game()
                except Exception as exc:
                    print(
                        f"Could not start game {seq} ({exc!r}); "
                        f"ending batch after {len(records)} game(s)."
                    )
                    break
            policy = policy_factory()
            try:
                result, ended_early = _play_browser_game(env, policy, wordlist.load_answers())
            except Exception as exc:
                print(f"Game {seq} failed ({exc!r}); continuing.")
                continue
            answers: list[str] = []
            if ended_early is None:
                try:
                    answers = env.read_answers()
                except Exception as exc:
                    print(f"Game {seq}: answer scrape failed ({exc!r}); logging without answers.")
            if ended_early is not None:
                from quordle.browser.browser_env import GuessRejected

                reason = (
                    f"the site rejected a guess: {ended_early}"
                    if isinstance(ended_early, GuessRejected)
                    else f"a transient API error interrupted play: {ended_early!r}"
                )
                print(
                    f"Browser game {seq} ended early after {len(result.guesses)} "
                    f"guess(es) -- {reason}."
                )
            record = _browser_record(
                result,
                ended_early,
                seq=seq,
                date=date,
                answers=answers,
                fallbacks=getattr(policy, "fallback_count", 0),
                metadata=metadata,
            )
            records.append(record)
            if out is not None:
                append_jsonl(out, [record])  # persist immediately -- crash/kill safe
    return records


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Play Quordle games and log them.")
    parser.add_argument("-n", "--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=DEFAULT_LOG)
    parser.add_argument("--date", default="2026-08-01")
    parser.add_argument("--player", choices=["heuristic", "claude", "gemini"], default="heuristic")
    parser.add_argument("--assist", choices=["none", "constraints", "candidates"], default="none")
    parser.add_argument(
        "--model",
        default=None,
        help="model id; defaults per player (claude: claude-sonnet-5, gemini: gemini-2.5-flash)",
    )
    parser.add_argument("--env", choices=["sim", "browser"], default="sim")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--fixed-openers",
        type=int,
        default=2,
        help="play this many precomputed openers with no provider call before "
        "handing off (heuristic: greedy; claude: the LLM); 0 recovers pure-LLM",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    factory, metadata = build_policy_factory(
        args.player, args.assist, args.model, args.fixed_openers
    )

    if args.env == "browser":
        records = run_browser_games(
            factory,
            count=args.count,
            start_seq=next_seq(args.out),
            date=args.date,
            allowed=wordlist.load_allowed(),
            headless=not args.headed,
            metadata={**metadata, "mode": "browser"},
            out=args.out,  # append each game as it finishes (issue #26)
        )
        print(f"Appended {len(records)} {args.player} browser game(s) to {args.out}")
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
        out=args.out,  # append each game as it finishes (issue #29)
    )
    print(f"Appended {len(records)} {args.player} games to {args.out}")


if __name__ == "__main__":
    main()
