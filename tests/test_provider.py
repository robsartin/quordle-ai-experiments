import os

import pytest

from quordle.provider import GuessResponse, MockProvider


def test_guess_response_schema():
    r = GuessResponse(reasoning="because", guess="CRANE")
    assert r.guess == "CRANE"


def test_mock_provider_returns_scripted_guesses_in_order():
    provider = MockProvider(["CRANE", "SLATE"])
    assert provider.next_guess("prompt").guess == "CRANE"
    assert provider.next_guess("prompt").guess == "SLATE"
    assert provider.next_guess("prompt").guess == "SLATE"  # repeats the last


@pytest.mark.skipif(
    os.getenv("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1 to hit the live API"
)
def test_claude_provider_returns_a_five_letter_word():
    from quordle.provider import ClaudeProvider

    resp = ClaudeProvider().next_guess("Reply with any common 5-letter English word as your guess.")
    assert len(resp.guess.strip()) == 5


def test_claude_provider_default_max_tokens_is_generous():
    from quordle.provider import ClaudeProvider

    # opus-5 thinks by default; the token budget must leave room for the
    # structured output after thinking. Construct offline (no network on ctor).
    provider = ClaudeProvider()
    assert provider._max_tokens >= 16000
