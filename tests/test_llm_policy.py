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


def test_excluded_word_is_never_returned_even_if_provider_proposes_it():
    # The site rejected CRANE; even though the provider proposes it again
    # (e.g. it hasn't learned better), choose() must reprompt/fall through
    # rather than returning it.
    policy = LLMPolicy(MockProvider(["CRANE", "SLATE"]))
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    guess = policy.choose(boards, [], ALLOWED, remaining=9, excluded=frozenset({"CRANE"}))
    assert guess == "SLATE"
    assert guess not in {"CRANE"}


def test_fallback_excludes_rejected_words_from_its_pool():
    # Provider keeps proposing the excluded word; fallback must not choose it,
    # even though it's the min() of the unfiltered active-candidate pool.
    policy = LLMPolicy(MockProvider(["CRANE"]), max_retries=1)
    boards = [Board(frozenset({"CRANE", "SLATE", "GRAPE"}))]
    guess = policy.choose(boards, [], ALLOWED, remaining=9, excluded=frozenset({"CRANE"}))
    assert guess != "CRANE"
    assert guess in {"SLATE", "GRAPE"}
    assert policy.fallback_count == 1


def test_fallback_falls_back_to_allowed_when_excluding_empties_candidate_pool():
    # Degenerate case: every active candidate is excluded. Fall back to the
    # (excluded-filtered) allowed set rather than crashing on pool[0].
    policy = LLMPolicy(MockProvider(["ZZZZZ"]), max_retries=0)
    boards = [Board(frozenset({"CRANE"}))]
    allowed = frozenset({"CRANE", "SLATE"})
    guess = policy.choose(boards, [], allowed, remaining=9, excluded=frozenset({"CRANE"}))
    assert guess == "SLATE"


def test_render_prompt_shows_feedback_and_candidates():
    boards = [Board(frozenset({"CRANE", "GRAPE"}))]
    history = [TurnFeedback("SLATE", [(X, Y, Y, X, Y)])]
    text = render_prompt(boards, history, Assist.CANDIDATES, remaining=8)
    assert "SLATE" in text
    assert "Board 1" in text
    assert "CRANE" in text  # candidate list included (set is small)
