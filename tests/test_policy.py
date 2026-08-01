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
