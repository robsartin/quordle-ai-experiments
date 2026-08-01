import json
import random

from quordle import wordlist
from quordle.engine import BoardState, TurnResult
from quordle.policy import FixedOpenersThenGreedy
from quordle.runner import append_jsonl, run_browser_game, run_game, run_many, sample_answers
from quordle.scoring import score


def test_sample_answers_distinct():
    picks = sample_answers(random.Random(1), wordlist.load_answers(), count=4)
    assert len(picks) == 4 and len(set(picks)) == 4


def test_run_game_produces_schema_valid_record():
    record = run_game(
        ["CRANE", "SLATE", "PLATE", "GRAPE"],
        FixedOpenersThenGreedy(),
        seq=1,
        date="2026-08-01",
        allowed=wordlist.load_allowed(),
    )
    assert record["seq"] == 1 and record["mode"] == "sim" and record["maxGuesses"] == 9
    assert record["totalGuessesUsed"] == len(record["guesses"])
    assert len(record["words"]) == 4
    for i, w in enumerate(record["words"], start=1):
        assert w["board"] == i and w["answer"].isupper()
        assert isinstance(w["solvedOnGuess"], int)
    assert record["boardsSolved"] == sum(1 for w in record["words"] if w["solvedOnGuess"])
    assert record["won"] == (record["boardsSolved"] == 4)


def test_run_game_records_a_loss():
    # A single guess (SLATE, the fixed opener) can't solve four boards whose
    # answers all differ from it, so the game ends unsolved: won is False,
    # every board's solvedOnGuess is 0, and boardsSolved is under 4.
    record = run_game(
        ["CRANE", "PLATE", "GRAPE", "STOMP"],
        FixedOpenersThenGreedy(),
        seq=1,
        date="2026-08-01",
        allowed=wordlist.load_allowed(),
        max_guesses=1,
    )
    assert record["won"] is False
    assert record["boardsSolved"] < 4
    assert record["boardsSolved"] == 0
    assert all(w["solvedOnGuess"] == 0 for w in record["words"])


def test_run_game_merges_metadata():
    record = run_game(
        ["CRANE", "SLATE", "PLATE", "GRAPE"],
        FixedOpenersThenGreedy(),
        seq=1,
        date="2026-08-01",
        allowed=wordlist.load_allowed(),
        metadata={"player": "heuristic"},
    )
    assert record["player"] == "heuristic"


def test_run_many_deterministic_for_a_seed():
    answers, allowed = wordlist.load_answers(), wordlist.load_allowed()
    a = run_many(
        3,
        seed=7,
        policy_factory=FixedOpenersThenGreedy,
        answers=answers,
        allowed=allowed,
        start_seq=1,
        date="2026-08-01",
    )
    b = run_many(
        3,
        seed=7,
        policy_factory=FixedOpenersThenGreedy,
        answers=answers,
        allowed=allowed,
        start_seq=1,
        date="2026-08-01",
    )
    assert [g["words"] for g in a] == [g["words"] for g in b]


def test_append_jsonl_round_trips(tmp_path):
    path = tmp_path / "games.jsonl"
    records = [{"seq": 1, "guesses": ["SLATE"]}]
    append_jsonl(str(path), records)
    append_jsonl(str(path), records)
    lines = path.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["seq"] == 1


def test_build_policy_factory_heuristic():
    from quordle.runner import build_policy_factory

    factory, metadata = build_policy_factory("heuristic", "none", "claude-opus-5")
    policy = factory()
    assert metadata["player"] == "heuristic"
    assert hasattr(policy, "choose")


def test_build_policy_factory_claude_metadata():
    from quordle.runner import build_policy_factory

    _factory, metadata = build_policy_factory("claude", "constraints", "claude-opus-5")
    assert metadata == {
        "player": "claude",
        "model": "claude-opus-5",
        "assist": "constraints",
        "mode": "claude",
    }


def test_env_choice_default_and_parse():
    from quordle.runner import build_arg_parser

    parser = build_arg_parser()
    assert parser.parse_args([]).env == "sim"
    assert parser.parse_args(["--env", "browser", "--headed"]).env == "browser"
    assert parser.parse_args(["--env", "browser", "--headed"]).headed is True


class FakeBrowserEnv:
    """A scripted stand-in for BrowserEnv -- no real browser -- implementing
    the Environment protocol plus BrowserEnv's own context-manager methods,
    so it can be injected via `run_browser_game`'s `env_factory`. Optionally
    raises GuessRejected on a specific submit call, to exercise the
    site-rejection recovery path (see runner._play_browser_game) offline.
    """

    def __init__(self, answer, allowed, max_guesses=9, reject_on_submit=None):
        self._answer = answer.upper()
        self.allowed = allowed
        self.max_guesses = max_guesses
        self.num_boards = 1
        self._used = 0
        self._solved_on = None
        self._submit_calls = 0
        self._reject_on_submit = reject_on_submit  # 1-based submit() call number

    def remaining_guesses(self):
        return self.max_guesses - self._used

    def finished(self):
        return self._used >= self.max_guesses or self._solved_on is not None

    def submit(self, guess):
        from quordle.browser.browser_env import GuessRejected

        self._submit_calls += 1
        if self._submit_calls == self._reject_on_submit:
            raise GuessRejected(f"guess not accepted by the site: {guess!r}")
        guess = guess.upper()
        self._used += 1
        pattern = score(guess, self._answer)
        if guess == self._answer:
            self._solved_on = self._used
            return TurnResult(self._used, [BoardState(0, True, self._used, pattern)])
        return TurnResult(self._used, [BoardState(0, False, None, pattern)])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class FixedGuessPolicy:
    def __init__(self, guesses):
        self._guesses = guesses

    def choose(self, boards, history, allowed, remaining):
        return self._guesses[len(history)]


def test_run_browser_game_record_shape_offline():
    # Exercises run_browser_game's injectable env_factory (no real browser)
    # to verify the mode:"browser" record shape without RUN_BROWSER_TESTS.
    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    record = run_browser_game(
        FixedGuessPolicy(["SLATE"]),
        seq=5,
        date="2026-08-01",
        allowed=allowed,
        headless=True,
        metadata={"player": "heuristic"},
        env_factory=lambda: env,
    )
    assert record["seq"] == 5 and record["mode"] == "browser" and record["maxGuesses"] == 9
    assert record["totalGuessesUsed"] == len(record["guesses"]) == 1
    assert record["guesses"] == ["SLATE"]
    assert record["words"] == [{"board": 1, "answer": "", "solvedOnGuess": 1}]
    assert record["boardsSolved"] == 1
    assert record["won"] is True
    assert record["player"] == "heuristic"
    assert "endedEarly" not in record


def test_run_browser_game_logs_partial_result_on_guess_rejected():
    # The site rejects the 2nd guess; the game should end early with a
    # (won=False) record reflecting the 1 accepted guess, not crash or lose
    # that guess's progress.
    allowed = frozenset({"SLATE", "SNAKE"})
    env = FakeBrowserEnv("CRANE", allowed, reject_on_submit=2)
    record = run_browser_game(
        FixedGuessPolicy(["SLATE", "SNAKE"]),
        seq=6,
        date="2026-08-01",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    assert record["endedEarly"] is True
    assert record["guesses"] == ["SLATE"]
    assert record["totalGuessesUsed"] == 1
    assert record["boardsSolved"] == 0
    assert record["won"] is False
