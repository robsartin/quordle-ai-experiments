"""Top-up sweep (issue #39): keep playing until N games have *completed*."""


def test_backoff_delay_doubles_per_consecutive_throttle_up_to_the_cap():
    from quordle.sweep import backoff_delay

    delays = [backoff_delay(n, base=5.0, cap=60.0) for n in (1, 2, 3, 4, 5, 6)]
    assert delays == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0]


def test_backoff_delay_is_zero_when_nothing_has_been_throttled():
    from quordle.sweep import backoff_delay

    assert backoff_delay(0, base=5.0, cap=60.0) == 0.0


def test_puzzle_stream_is_deterministic_for_a_seed():
    from itertools import islice

    from quordle import wordlist
    from quordle.sweep import puzzle_stream

    answers = wordlist.load_answers()
    a = list(islice(puzzle_stream(7, answers, done=set()), 5))
    b = list(islice(puzzle_stream(7, answers, done=set()), 5))
    assert a == b
    assert all(len(p) == 4 and len(set(p)) == 4 for p in a)


def test_puzzle_stream_skips_puzzles_already_completed():
    # The dedupe guarantee: re-running the same seed must not replay a puzzle the
    # log already holds -- it advances past it to the next fresh one.
    from itertools import islice

    from quordle import wordlist
    from quordle.sweep import puzzle_stream

    answers = wordlist.load_answers()
    fresh = list(islice(puzzle_stream(7, answers, done=set()), 4))
    done = {tuple(fresh[0]), tuple(fresh[2])}
    resumed = list(islice(puzzle_stream(7, answers, done=done), 2))
    assert resumed == [fresh[1], fresh[3]]


def test_puzzle_stream_never_repeats_a_puzzle_within_one_stream():
    from itertools import islice

    from quordle.sweep import puzzle_stream

    # Only 5 distinct words -> sampling 4 gives at most 5 distinct sets; the stream
    # must yield each at most once and then end rather than loop forever.
    words = ("AAAAA", "BBBBB", "CCCCC", "DDDDD", "EEEEE")
    seen = [tuple(sorted(p)) for p in islice(puzzle_stream(1, words, done=set()), 50)]
    assert len(seen) == len(set(seen)) <= 5


def _record(answers, **extra):
    base = {
        "seq": 1,
        "mode": "gemini",
        "player": "gemini",
        "model": "gemini-3.5-flash",
        "assist": "none",
        "openers": 2,
        "words": [{"board": i + 1, "answer": a, "solvedOnGuess": 3} for i, a in enumerate(answers)],
    }
    base.update(extra)
    return base


_CONFIG = {
    "player": "gemini",
    "model": "gemini-3.5-flash",
    "assist": "none",
    "mode": "gemini",
    "openers": 2,
}


def _write_log(path, records):
    import json

    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def test_completed_puzzles_counts_only_this_configs_finished_games(tmp_path):
    from quordle.sweep import completed_puzzles

    log = tmp_path / "games.jsonl"
    _write_log(
        log,
        [
            _record(["CRANE", "SLATE", "PLATE", "GRAPE"]),  # counts
            _record(["AAAAA", "BBBBB", "CCCCC", "DDDDD"], assist="candidates"),  # other config
            _record(["EEEEE", "FFFFF", "GGGGG", "HHHHH"], model="gemini-3.5-pro"),  # other model
            _record(["IIIII", "JJJJJ", "KKKKK", "LLLLL"], endedEarly=True),  # not completed
            _record(["MMMMM", "NNNNN", "OOOOO", "PPPPP"], mode="browser"),  # other mode
            _record(["STOMP", "BLOAT", "FROST", "CLIMB"], won=False),  # a loss still completed
        ],
    )
    assert completed_puzzles(str(log), _CONFIG) == [
        ("CRANE", "GRAPE", "PLATE", "SLATE"),
        ("BLOAT", "CLIMB", "FROST", "STOMP"),
    ]


def test_completed_puzzles_is_empty_for_a_missing_log(tmp_path):
    from quordle.sweep import completed_puzzles

    assert completed_puzzles(str(tmp_path / "nope.jsonl"), _CONFIG) == []


def test_completed_puzzles_ignores_blank_lines(tmp_path):
    from quordle.sweep import completed_puzzles

    log = tmp_path / "games.jsonl"
    log.write_text(
        "\n" + __import__("json").dumps(_record(["CRANE", "SLATE", "PLATE", "GRAPE"])) + "\n\n"
    )
    assert len(completed_puzzles(str(log), _CONFIG)) == 1
