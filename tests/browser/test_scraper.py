import pytest

from quordle.browser import scraper
from quordle.scoring import Mark

G, Y, X = Mark.GREEN, Mark.YELLOW, Mark.GREY

# Real aria-label rows captured from beta.quordle.com (guess CURIO, then PLANE).
CURIO_B2 = [
    "'C' (letter 1) is in a different spot",
    "'U' (letter 2) is incorrect",
    "'R' (letter 3) is correct",
    "'I' (letter 4) is in a different spot",
    "'O' (letter 5) is incorrect",
]  # -> Y . G Y .
CURIO_B4 = [
    "'C' (letter 1) is incorrect",
    "'U' (letter 2) is incorrect",
    "'R' (letter 3) is correct",
    "'I' (letter 4) is correct",
    "'O' (letter 5) is incorrect",
]  # -> . . G G .
BLANK = [f"'Blank' (letter {i}) is being guessed" for i in range(1, 6)]
FUTURE = [f"'Blank' (letter {i}) is a future guess" for i in range(1, 6)]
# Once a board is SOLVED/complete, its remaining rows switch to this label
# instead of "is a future guess" (found live -- a real game crashed on it
# before scraper.tile_mark learned to recognize it).
NEVER_GUESSABLE = [
    f"'Blank' (letter {i}) is never guessable (board is complete)" for i in range(1, 6)
]
ALL_CORRECT = [f"'S' (letter {i}) is correct" for i in range(1, 6)]  # a solved row


def test_tile_mark_all_three_and_blank() -> None:
    assert scraper.tile_mark("'R' (letter 3) is correct") is Mark.GREEN
    assert scraper.tile_mark("'C' (letter 1) is in a different spot") is Mark.YELLOW
    assert scraper.tile_mark("'U' (letter 2) is incorrect") is Mark.GREY
    assert scraper.tile_mark("'Blank' (letter 1) is being guessed") is None
    # Rows further down the board than the one currently being typed use a
    # distinct "future guess" label on the live site (found via
    # RUN_BROWSER_TESTS=1 live validation); these are also unplayed.
    assert scraper.tile_mark("'Blank' (letter 1) is a future guess") is None
    # Once a board is solved/complete, its never-to-be-played rows use yet
    # another label; a live game crashed on this exact string before the fix.
    assert scraper.tile_mark("'Blank' (letter 1) is never guessable (board is complete)") is None


def test_parse_row_real_rows() -> None:
    assert scraper.parse_row(CURIO_B2) == (Y, X, G, Y, X)
    assert scraper.parse_row(CURIO_B4) == (X, X, G, G, X)


def test_parse_row_rejects_unplayed() -> None:
    with pytest.raises(ValueError):
        scraper.parse_row(BLANK)


def test_row_played() -> None:
    assert scraper.row_played(CURIO_B2) is True
    assert scraper.row_played(BLANK) is False
    assert scraper.row_played(FUTURE) is False
    assert scraper.row_played(NEVER_GUESSABLE) is False


def test_count_played_is_max_across_boards() -> None:
    boards = [
        [CURIO_B2, CURIO_B4] + [BLANK] * 7,  # 2 played
        [CURIO_B4] + [BLANK] * 8,  # 1 played
        [BLANK] * 9,  # 0 played
        [CURIO_B2, CURIO_B4] + [BLANK] * 7,  # 2 played
    ]
    assert scraper.count_played(boards) == 2


def test_read_turn_unsolved_and_solved() -> None:
    # board 0 solved on row 2 (this turn); board 1 not solved
    boards = [
        [CURIO_B4, ALL_CORRECT] + [BLANK] * 7,
        [CURIO_B2, CURIO_B4] + [BLANK] * 7,
    ]
    states = scraper.read_turn(boards, guesses_used=2)
    assert states[0].index == 0
    assert states[0].solved is True and states[0].solved_on == 2
    assert states[0].pattern == (G, G, G, G, G)  # solved THIS turn -> pattern present
    assert states[1].solved is False and states[1].solved_on is None
    assert states[1].pattern == (X, X, G, G, X)  # this turn's CURIO_B4 row


def test_read_turn_already_solved_board_pattern_none() -> None:
    # board solved on row 1; on turn 2 it reports pattern None
    boards = [[ALL_CORRECT, BLANK] + [BLANK] * 7]
    states = scraper.read_turn(boards, guesses_used=2)
    assert states[0].solved is True and states[0].solved_on == 1
    assert states[0].pattern is None


def test_solved_on_public() -> None:
    # `_solved_on` was promoted to a public `solved_on`; a direct test for it
    # (previously only exercised indirectly through read_turn).
    assert scraper.solved_on([CURIO_B4, ALL_CORRECT] + [BLANK] * 7) == 2
    assert scraper.solved_on([CURIO_B2, CURIO_B4] + [BLANK] * 7) is None


def test_completed_board_real_rows_then_never_guessable() -> None:
    # A SOLVED/complete board: real feedback rows up to its solve (row 2),
    # then "never guessable" for the rest -- the exact shape that crashed a
    # live game before tile_mark learned to recognize that label.
    board = [CURIO_B4, ALL_CORRECT] + [NEVER_GUESSABLE] * 7
    assert scraper.row_played(board[0]) is True
    assert scraper.row_played(board[1]) is True
    assert all(scraper.row_played(row) is False for row in board[2:])
    assert scraper.count_played([board]) == 2
    assert scraper.solved_on(board) == 2
    states = scraper.read_turn([board], guesses_used=2)
    assert states[0].solved is True and states[0].solved_on == 2
    assert states[0].pattern == (G, G, G, G, G)
