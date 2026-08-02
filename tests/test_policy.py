from quordle.board import Board
from quordle.engine import TurnFeedback
from quordle.policy import DEFAULT_OPENERS, FixedOpenersThenGreedy


def _fb(guess):
    return TurnFeedback(guess, [None])


def test_plays_openers_in_order():
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [Board(frozenset({"CRANE", "TRACE"}))]
    assert policy.choose(boards, [], frozenset(), remaining=9) == "SLATE"
    assert policy.choose(boards, [_fb("SLATE")], frozenset(), remaining=8) == "CURIO"


def test_greedy_solves_a_pinned_board():
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [
        Board(frozenset()),
        Board(frozenset({"GRAPE"})),
        Board(frozenset({"CRANE", "TRACE"})),
    ]
    history = [_fb("SLATE"), _fb("CURIO")]
    assert policy.choose(boards, history, frozenset(), remaining=7) == "GRAPE"


def test_greedy_is_deterministic():
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [Board(frozenset({"CRANE", "TRACE", "PLATE", "GRAPE"}))]
    history = [_fb("SLATE"), _fb("CURIO")]
    a = policy.choose(boards, history, frozenset(), remaining=7)
    b = policy.choose(boards, history, frozenset(), remaining=7)
    assert a == b


def test_default_openers_exposed():
    assert DEFAULT_OPENERS == ["SLATE", "CURIO"]


def test_excluded_opener_falls_through_to_greedy():
    # If the site rejected the opener, don't re-propose it -- fall through to
    # the greedy pool immediately, even on the first turn.
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [Board(frozenset({"CRANE", "TRACE"}))]
    guess = policy.choose(boards, [], frozenset(), remaining=9, excluded=frozenset({"SLATE"}))
    assert guess != "SLATE"
    assert guess in {"CRANE", "TRACE"}


def test_excluded_pinned_candidate_falls_through_to_pool():
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [
        Board(frozenset()),
        Board(frozenset({"GRAPE"})),
        Board(frozenset({"CRANE", "TRACE"})),
    ]
    history = [_fb("SLATE"), _fb("CURIO")]
    guess = policy.choose(boards, history, frozenset(), remaining=7, excluded=frozenset({"GRAPE"}))
    assert guess != "GRAPE"


def test_excluded_pool_falls_back_to_allowed():
    # If excluding candidates empties the active pool entirely, fall back to
    # the full allowed set (minus excluded), rather than crashing on min([]).
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [Board(frozenset({"CRANE"}))]
    history = [_fb("SLATE"), _fb("CURIO")]
    allowed = frozenset({"CRANE", "TRACE", "GRAPE"})
    guess = policy.choose(boards, history, allowed, remaining=7, excluded=frozenset({"CRANE"}))
    assert guess in allowed - {"CRANE"}


def test_excluded_pool_and_allowed_both_empty_falls_back_to_full_allowed():
    # Degenerate case: excluding leaves nothing even in `allowed`. Fall back
    # to the unfiltered allowed set rather than crashing.
    policy = FixedOpenersThenGreedy(["SLATE", "CURIO"])
    boards = [Board(frozenset({"CRANE"}))]
    history = [_fb("SLATE"), _fb("CURIO")]
    allowed = frozenset({"CRANE"})
    guess = policy.choose(boards, history, allowed, remaining=7, excluded=frozenset({"CRANE"}))
    assert guess == "CRANE"
