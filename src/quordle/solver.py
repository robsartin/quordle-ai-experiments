"""Drive a Policy against any Environment, answer-blind (ADR 13)."""

from dataclasses import dataclass

from quordle.board import Board
from quordle.engine import Environment, TurnFeedback
from quordle.policy import Policy


@dataclass
class SolveResult:
    guesses: list[str]
    solved_on: list[int | None]


def solve(env: Environment, policy: Policy, answers: tuple[str, ...] | list[str]) -> SolveResult:
    full = frozenset(w.upper() for w in answers)
    boards = [Board(full) for _ in range(env.num_boards)]
    guesses: list[str] = []
    history: list[TurnFeedback] = []
    solved_on: list[int | None] = [None] * env.num_boards

    while not env.finished():
        guess = policy.choose(boards, history, env.allowed, env.remaining_guesses())
        guesses.append(guess)
        result = env.submit(guess)
        history.append(TurnFeedback(guess, [state.pattern for state in result.boards]))
        for i, state in enumerate(result.boards):
            if state.solved:
                if solved_on[i] is None:
                    solved_on[i] = state.solved_on
                boards[i] = Board(frozenset())
            elif state.pattern is not None:
                boards[i] = boards[i].filter(guess, state.pattern)

    return SolveResult(guesses, solved_on)
