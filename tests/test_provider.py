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


def test_claude_provider_read_timeout_covers_thinking_but_is_bounded():
    from quordle.provider import ClaudeProvider

    # Real mid-game calls with default extended thinking take ~70s, so the
    # timeout must comfortably exceed that (or it kills legit calls), yet stay
    # well under the SDK's 600s default so a true stall still fails in bounded
    # time and is caught by the graceful-recovery path. Offline (no network).
    provider = ClaudeProvider()
    t = provider._client.timeout
    read = t if isinstance(t, (int, float)) else t.read
    assert read is not None and 120 <= read <= 300


def test_claude_provider_prefers_ipv4():
    from quordle.provider import ClaudeProvider

    # Every observed API stall was a wedged IPv6 socket; binding the local
    # address to the IPv4 wildcard forces IPv4 and sidesteps that route.
    provider = ClaudeProvider()
    transport = provider._client._client._transport
    assert transport._pool._local_address == "0.0.0.0"
