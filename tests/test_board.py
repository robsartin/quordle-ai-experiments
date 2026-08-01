from quordle.board import Board
from quordle.scoring import score


def test_filter_keeps_only_consistent_candidates():
    board = Board(frozenset({"CRANE", "TRACE", "PLATE", "SLATE"}))
    pattern = score("CRANE", "TRACE")
    kept = board.filter("CRANE", pattern)
    assert "TRACE" in kept.candidates
    assert "SLATE" not in kept.candidates


def test_filter_to_single_answer():
    board = Board(frozenset({"CRANE", "TRACE"}))
    kept = board.filter("CRANE", score("CRANE", "CRANE"))
    assert kept.candidates == frozenset({"CRANE"})
