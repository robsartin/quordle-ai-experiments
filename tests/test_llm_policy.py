from quordle.board import Board
from quordle.engine import TurnFeedback
from quordle.llm_policy import Assist, LLMPolicy, render_prompt
from quordle.provider import MockProvider
from quordle.scoring import Mark

ALLOWED = frozenset({"CRANE", "SLATE", "GRAPE"})
G, Y, X = Mark.GREEN, Mark.YELLOW, Mark.GREY


def test_returns_valid_provider_guess():
    policy = LLMPolicy(MockProvider(["CRANE"]))
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    assert policy.choose(boards, [], ALLOWED, remaining=9) == "CRANE"
    assert policy.fallback_count == 0


def test_reprompts_on_invalid_then_accepts():
    policy = LLMPolicy(MockProvider(["ZZZZZ", "CRANE"]))
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    assert policy.choose(boards, [], ALLOWED, remaining=9) == "CRANE"
    assert policy.fallback_count == 0


def test_falls_back_after_exhausting_retries():
    policy = LLMPolicy(MockProvider(["ZZZZZ"]), max_retries=2)
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    guess = policy.choose(boards, [], ALLOWED, remaining=9)
    assert guess == "CRANE"  # deterministic min of candidates
    assert policy.fallback_count == 1


def test_render_prompt_shows_feedback_and_candidates():
    boards = [Board(frozenset({"CRANE", "GRAPE"}))]
    history = [TurnFeedback("SLATE", [(X, Y, Y, X, Y)])]
    text = render_prompt(boards, history, Assist.CANDIDATES, remaining=8)
    assert "SLATE" in text
    assert "Board 1" in text
    assert "CRANE" in text  # candidate list included (set is small)
