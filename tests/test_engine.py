import pytest

from quordle.engine import SimEngine
from quordle.scoring import Mark

ALLOWED = frozenset({"CRANE", "SLATE", "PLATE", "GRAPE"})


def make_engine(max_guesses=9):
    return SimEngine(["CRANE", "SLATE", "PLATE", "GRAPE"], ALLOWED, max_guesses=max_guesses)


def test_solving_a_board_records_solved_on():
    eng = make_engine()
    result = eng.submit("CRANE")
    assert result.guesses_used == 1
    assert result.boards[0].solved is True
    assert result.boards[0].solved_on == 1
    assert result.boards[0].pattern == (Mark.GREEN,) * 5
    assert result.boards[1].solved is False


def test_already_solved_board_reports_no_pattern():
    eng = make_engine()
    eng.submit("CRANE")
    result = eng.submit("SLATE")
    assert result.boards[0].solved is True
    assert result.boards[0].pattern is None


def test_invalid_guess_rejected():
    eng = make_engine()
    with pytest.raises(ValueError):
        eng.submit("ZZZZZ")
    with pytest.raises(ValueError):
        eng.submit("CAT")


def test_finished_after_max_guesses():
    eng = make_engine(max_guesses=1)
    eng.submit("GRAPE")
    assert eng.finished() is True
    assert eng.remaining_guesses() == 0
    with pytest.raises(RuntimeError):
        eng.submit("SLATE")


def test_finished_when_all_solved():
    eng = SimEngine(["CRANE", "CRANE", "CRANE", "CRANE"], ALLOWED, max_guesses=9)
    eng.submit("CRANE")
    assert eng.finished() is True
