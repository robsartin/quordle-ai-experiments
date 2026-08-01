import json
import random

from quordle import wordlist
from quordle.policy import FixedOpenersThenGreedy
from quordle.runner import append_jsonl, run_game, run_many, sample_answers


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
