import os

import pytest

from quordle.provider import NoStructuredOutput


def test_gemini_provider_default_model_is_flash(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # ctor needs a key present
    from quordle.gemini_provider import GeminiProvider

    assert GeminiProvider()._model == "gemini-3.5-flash"


def test_gemini_provider_read_timeout_is_bounded(monkeypatch):
    # HttpOptions.timeout is in milliseconds; mirror ClaudeProvider's 150s bound
    # so a real thinking call survives but a true stall still fails in bounded
    # time for the runner's transient-skip path. Offline (no network).
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from quordle.gemini_provider import GeminiProvider
    from quordle.provider import _REQUEST_TIMEOUT_S

    provider = GeminiProvider()
    timeout = provider._client._api_client._http_options.timeout
    assert timeout == int(_REQUEST_TIMEOUT_S * 1000)
    assert 120_000 <= timeout <= 300_000


def test_gemini_provider_raises_no_structured_output_on_unparseable(monkeypatch):
    # When the model returns nothing parseable, response.parsed is None (or not a
    # GuessResponse). The provider must raise the shared NoStructuredOutput (a
    # skippable per-call failure), not crash a batch. Offline.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from quordle.gemini_provider import GeminiProvider

    provider = GeminiProvider()

    class _Resp:
        parsed = None

    monkeypatch.setattr(provider._client.models, "generate_content", lambda **kw: _Resp())
    with pytest.raises(NoStructuredOutput):
        provider.next_guess("anything")


@pytest.mark.skipif(
    os.getenv("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1 to hit the live API"
)
def test_gemini_provider_returns_a_five_letter_word():
    from quordle.gemini_provider import GeminiProvider

    resp = GeminiProvider().next_guess("Reply with any common 5-letter English word as your guess.")
    assert len(resp.guess.strip()) == 5


def test_gemini_provider_retries_throttle_statuses_with_bounded_attempts(monkeypatch):
    # Issue #39 option C: retry 429/503/504 inside the SDK to cut the skip rate at
    # the source. Attempts stay small: each attempt can take up to the 150s read
    # timeout, so the worst-case wall time per call is attempts * 150s + backoff.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    from quordle.gemini_provider import GeminiProvider

    retry = GeminiProvider()._client._api_client._http_options.retry_options
    assert retry is not None
    assert {429, 503, 504} <= set(retry.http_status_codes or [])
    assert retry.attempts is not None and 2 <= retry.attempts <= 4
    assert retry.max_delay is not None and retry.max_delay <= 30
