from quordle.engine import BoardState, TurnResult
from quordle.scoring import score
from quordle.solver import solve


class ScriptedEnv:
    """A one-board environment with a fixed hidden answer, for solver testing."""

    def __init__(self, answer, allowed, max_guesses=9):
        self._answer = answer.upper()
        self.allowed = allowed
        self.max_guesses = max_guesses
        self.num_boards = 1
        self._used = 0
        self._solved_on = None

    def remaining_guesses(self):
        return self.max_guesses - self._used

    def finished(self):
        return self._used >= self.max_guesses or self._solved_on is not None

    def submit(self, guess):
        guess = guess.upper()
        self._used += 1
        if self._solved_on is not None:
            return TurnResult(self._used, [BoardState(0, True, self._solved_on, None)])
        pattern = score(guess, self._answer)
        if guess == self._answer:
            self._solved_on = self._used
            return TurnResult(self._used, [BoardState(0, True, self._used, pattern)])
        return TurnResult(self._used, [BoardState(0, False, None, pattern)])


class FixedGuessPolicy:
    def __init__(self, guesses):
        self._guesses = guesses

    def choose(self, boards, history, allowed, remaining):
        return self._guesses[len(history)]


def test_solve_records_guesses_and_solved_on():
    allowed = frozenset({"SLATE", "CRANE"})
    env = ScriptedEnv("CRANE", allowed)
    result = solve(env, FixedGuessPolicy(["SLATE", "CRANE"]), ["SLATE", "CRANE"])
    assert result.guesses == ["SLATE", "CRANE"]
    assert result.solved_on == [2]


def test_solve_stops_at_max_guesses_when_unsolved():
    allowed = frozenset({"SLATE", "CRANE"})
    env = ScriptedEnv("CRANE", allowed, max_guesses=1)
    result = solve(env, FixedGuessPolicy(["SLATE"]), ["SLATE", "CRANE"])
    assert result.guesses == ["SLATE"]
    assert result.solved_on == [None]
