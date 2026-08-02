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


def test_append_jsonl_backs_up_existing_log(tmp_path):
    # Durability (issue #11): the game log is gitignored and irreplaceable, and
    # was once externally truncated to empty. Each append first snapshots the
    # existing non-empty log to <path>.bak, leaving one recovery point.
    path = tmp_path / "games.jsonl"
    bak = tmp_path / "games.jsonl.bak"
    append_jsonl(str(path), [{"seq": 1}])  # file was absent -> nothing to back up
    assert not bak.exists()
    append_jsonl(str(path), [{"seq": 2}])  # existing 1-line log snapshotted first
    assert bak.exists()
    assert bak.read_text().strip() == json.dumps({"seq": 1})  # backup = pre-append state
    assert len(path.read_text().splitlines()) == 2  # main log still fully appended


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

    def __init__(
        self,
        answer,
        allowed,
        max_guesses=9,
        reject_on_submit=None,
        reject_words=frozenset(),
        fail_on_game=None,
        new_game_fails=False,
    ):
        self._answer = answer.upper()
        self.allowed = allowed
        self.max_guesses = max_guesses
        self.num_boards = 1
        self._used = 0
        self._solved_on = None
        self._submit_calls = 0
        self._reject_on_submit = reject_on_submit  # 1-based submit() call number
        self._reject_words = reject_words
        self.reject_count = 0  # how many submits the "site" refused (retry observability)
        self._game = 1
        self._fail_on_game = fail_on_game  # 1-based game index whose submit raises
        self._new_game_fails = new_game_fails

    def remaining_guesses(self):
        return self.max_guesses - self._used

    def finished(self):
        return self._used >= self.max_guesses or self._solved_on is not None

    def submit(self, guess):
        from quordle.browser.browser_env import GuessRejected

        if guess.upper() in self._reject_words:
            self.reject_count += 1
            raise GuessRejected(f"guess not accepted by the site: {guess!r}")
        if self._game == self._fail_on_game:
            raise RuntimeError(f"simulated browser failure on game {self._game}")
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

    def read_answers(self):
        return [self._answer] if self.finished() else []

    def new_game(self):
        if self._new_game_fails or not self.finished():
            raise RuntimeError("cannot start new game (not at game-over)")
        self._used = 0
        self._solved_on = None
        self._submit_calls = 0
        self._game += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class FixedGuessPolicy:
    def __init__(self, guesses):
        self._guesses = guesses

    def choose(self, boards, history, allowed, remaining, excluded=frozenset()):
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
    assert record["words"] == [{"board": 1, "answer": "SLATE", "solvedOnGuess": 1}]
    assert record["boardsSolved"] == 1
    assert record["won"] is True
    assert record["player"] == "heuristic"
    assert "endedEarly" not in record


def test_browser_game_prints_per_guess_progress(capsys):
    # Unattended runs must show live progress, not silence. _play_browser_game
    # prints one line per accepted guess (browser-only, so sim runs stay quiet).
    allowed = frozenset({"CRANE", "SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    run_browser_game(
        FixedGuessPolicy(["CRANE", "SLATE"]),
        seq=7,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    out = capsys.readouterr().out
    assert "guess 1/9: CRANE -> 0/1 boards solved" in out
    assert "guess 2/9: SLATE -> 1/1 boards solved" in out


class TimeoutOnNthGuessPolicy:
    """Policy that raises anthropic.APITimeoutError on a chosen guess, to
    exercise the browser loop's transient-API-stall recovery offline."""

    def __init__(self, guesses, raise_on):
        self._guesses = guesses
        self._raise_on = raise_on  # 1-based choose() call number
        self._calls = 0

    def choose(self, boards, history, allowed, remaining, excluded=frozenset()):
        self._calls += 1
        if self._calls == self._raise_on:
            import anthropic
            import httpx

            raise anthropic.APITimeoutError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            )
        return self._guesses[len(history)]


def test_browser_game_ends_gracefully_on_api_timeout():
    # A transient API stall (SDK retries exhausted -> APITimeoutError) must not
    # crash an unattended run: end the game with a partial (won=False) record
    # covering the guesses accepted before the stall, like GuessRejected.
    allowed = frozenset({"CRANE", "SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    record = run_browser_game(
        TimeoutOnNthGuessPolicy(["CRANE", "SLATE"], raise_on=2),
        seq=8,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    assert record["endedEarly"] is True
    assert record["guesses"] == ["CRANE"]
    assert record["totalGuessesUsed"] == 1
    assert record["boardsSolved"] == 0
    assert record["won"] is False


def test_run_browser_games_plays_count_games_and_logs_answers():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=3,
        start_seq=10,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    assert [r["seq"] for r in records] == [10, 11, 12]
    assert all(r["mode"] == "browser" and r["won"] is True for r in records)
    assert all(r["words"][0]["answer"] == "SLATE" for r in records)


def test_run_browser_games_ends_batch_after_a_mid_play_failure():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed, fail_on_game=2)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=3,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    # game 2 raises mid-play, leaving the page not at game-over, so the next
    # new_game() (for game 3) finds no "New Practice Game" button and raises
    # too -- ending the batch after game 1.
    assert [r["seq"] for r in records] == [1]


def test_run_browser_games_ends_batch_when_new_game_cannot_reset():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed, new_game_fails=True)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=3,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    # game 1 plays; new_game() for game 2 fails -> batch ends gracefully
    assert [r["seq"] for r in records] == [1]


def test_run_browser_games_appends_each_game_to_out(tmp_path):
    # Issue #26: with `out`, run_browser_games persists each game itself (not a
    # single at-end append by the caller), so the log fills in as games finish.
    from quordle.runner import run_browser_games

    out = tmp_path / "games.jsonl"
    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=3,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
        out=str(out),
    )
    lines = out.read_text().splitlines()
    assert [json.loads(line)["seq"] for line in lines] == [1, 2, 3]
    assert [r["seq"] for r in records] == [1, 2, 3]  # still returns the list too


def test_run_browser_games_persists_games_before_an_early_batch_end(tmp_path):
    # Crash/kill safety: a game failing mid-batch ends the batch, but the games
    # completed BEFORE it are already on disk -- not lost to an at-end append.
    from quordle.runner import run_browser_games

    out = tmp_path / "games.jsonl"
    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed, fail_on_game=3)
    run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=5,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
        out=str(out),
    )
    lines = out.read_text().splitlines()
    assert [json.loads(line)["seq"] for line in lines] == [1, 2]  # saved before the crash


def test_run_browser_game_exhausts_retries_then_logs_partial():
    # The site ALWAYS rejects SNAKE; FixedGuessPolicy keeps re-proposing it for
    # that turn (it ignores `excluded`), so every retry is also rejected and
    # the turn's retries exhaust. The game ends early with a (won=False) record
    # reflecting the 1 accepted guess, not crashing or losing that progress.
    from quordle.runner import MAX_REJECT_RETRIES

    allowed = frozenset({"SLATE", "SNAKE"})
    env = FakeBrowserEnv("CRANE", allowed, reject_words={"SNAKE"})
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
    # The rejected turn was actually RETRIED to exhaustion, not given up on the
    # first rejection: the site refused SNAKE MAX_REJECT_RETRIES + 1 times.
    # (Without the retry loop this would be 1 -- so this assertion is what makes
    # the test verify the feature rather than pass vacuously.)
    assert env.reject_count == MAX_REJECT_RETRIES + 1


class RetryPolicy:
    """Per turn, returns the first of its options not in `excluded`."""

    def __init__(self, plan):  # plan: list[list[str]] per turn
        self._plan = plan

    def choose(self, boards, history, allowed, remaining, excluded=frozenset()):
        for w in self._plan[len(history)]:
            if w not in excluded:
                return w
        return self._plan[len(history)][-1]


def test_run_browser_game_retries_and_continues_after_rejection():
    # The site rejects SNAKE; a policy that honors `excluded` retries within
    # the SAME turn with an alternative (SLATE) instead of ending the game.
    allowed = frozenset({"CRANE", "SLATE", "SNAKE"})
    env = FakeBrowserEnv("SLATE", allowed, reject_words={"SNAKE"})
    record = run_browser_game(
        RetryPolicy([["CRANE"], ["SNAKE", "SLATE"]]),
        seq=9,
        date="2026-08-01",
        allowed=allowed,
        headless=True,
        env_factory=lambda: env,
    )
    assert record["guesses"] == ["CRANE", "SLATE"]
    assert "endedEarly" not in record
    assert record["won"] is True


def test_run_browser_games_carries_browser_metadata():
    from quordle.runner import run_browser_games

    allowed = frozenset({"SLATE"})
    env = FakeBrowserEnv("SLATE", allowed)
    records = run_browser_games(
        lambda: FixedGuessPolicy(["SLATE"]),
        count=2,
        start_seq=1,
        date="2026-08-02",
        allowed=allowed,
        headless=True,
        metadata={"player": "claude", "mode": "browser"},
        env_factory=lambda: env,
    )
    assert len(records) == 2
    assert all(r["player"] == "claude" and r["mode"] == "browser" for r in records)
