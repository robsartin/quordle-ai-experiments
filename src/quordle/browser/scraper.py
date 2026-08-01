"""Pure parsing of quordle.com tile aria-labels into engine feedback (ADR 13)."""

from quordle.engine import BoardState
from quordle.scoring import Mark, Pattern


def tile_mark(label: str) -> Mark | None:
    if "is being guessed" in label:
        return None
    if "is correct" in label:
        return Mark.GREEN
    if "is in a different spot" in label:
        return Mark.YELLOW
    if "is incorrect" in label:
        return Mark.GREY
    raise ValueError(f"unrecognized tile label: {label!r}")


def parse_row(labels: list[str]) -> Pattern:
    marks: list[Mark] = []
    for label in labels:
        mark = tile_mark(label)
        if mark is None:
            raise ValueError(f"row is not fully played: {label!r}")
        marks.append(mark)
    if len(marks) != 5:
        raise ValueError(f"expected 5 tiles, got {len(marks)}")
    return (marks[0], marks[1], marks[2], marks[3], marks[4])


def row_played(labels: list[str]) -> bool:
    return all(tile_mark(label) is not None for label in labels)


def count_played(boards: list[list[list[str]]]) -> int:
    return max((sum(1 for row in board if row_played(row)) for board in boards), default=0)


def _solved_on(board: list[list[str]]) -> int | None:
    for i, row in enumerate(board, start=1):
        if row_played(row) and parse_row(row) == (Mark.GREEN,) * 5:
            return i
    return None


def read_turn(boards: list[list[list[str]]], guesses_used: int) -> list[BoardState]:
    states: list[BoardState] = []
    for index, board in enumerate(boards):
        solved_on = _solved_on(board)
        solved = solved_on is not None
        if solved and solved_on is not None and solved_on < guesses_used:
            pattern: Pattern | None = None  # solved on an earlier turn
        else:
            pattern = parse_row(board[guesses_used - 1])
        states.append(BoardState(index, solved, solved_on if solved else None, pattern))
    return states
