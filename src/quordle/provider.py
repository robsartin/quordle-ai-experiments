"""LLM providers behind one interface (ADR 17): a scripted mock and Claude."""

from typing import Protocol

from pydantic import BaseModel


class GuessResponse(BaseModel):
    reasoning: str
    guess: str


class LLMProvider(Protocol):
    def next_guess(self, prompt: str) -> GuessResponse: ...


class MockProvider:
    """Scripted provider for offline tests; repeats the final guess when exhausted."""

    def __init__(self, guesses: list[str], reasoning: str = "scripted") -> None:
        self._guesses = [g.upper() for g in guesses]
        self._reasoning = reasoning
        self._index = 0

    def next_guess(self, prompt: str) -> GuessResponse:
        guess = self._guesses[min(self._index, len(self._guesses) - 1)]
        self._index += 1
        return GuessResponse(reasoning=self._reasoning, guess=guess)


# Bound how long one call may block so a wedged TLS connection can't freeze an
# unattended run (the SDK's default read timeout is 600s). But real mid-game
# calls with default extended thinking measure ~63-75s, so the bound must sit
# well above that or it kills legit calls (a too-low 60s did exactly that);
# 150s gives ~2x margin over a real call while still failing a true stall in
# bounded time for the graceful-recovery path to catch.
_REQUEST_TIMEOUT_S = 150.0


class NoStructuredOutput(Exception):
    """Claude returned no parseable structured guess. Usually the extended
    thinking consumed max_tokens before the JSON guess was emitted. A
    per-call failure -- callers (the sim/browser loops) treat it as a
    skippable game, not a crash."""


class ClaudeProvider:
    """Claude via the official anthropic SDK, structured outputs, default claude-sonnet-5."""

    def __init__(self, model: str = "claude-sonnet-5", max_tokens: int = 24000) -> None:
        import anthropic
        import httpx

        # Prefer IPv4: every observed API stall was a wedged IPv6 socket
        # (blocked in _ssl__SSLSocket_read with no data). Binding the local
        # address to the IPv4 wildcard forces IPv4 connections, sidestepping
        # that route entirely; the timeout is the backstop if any read stalls.
        self._client = anthropic.Anthropic(
            timeout=_REQUEST_TIMEOUT_S,
            http_client=httpx.Client(
                transport=httpx.HTTPTransport(local_address="0.0.0.0"),
                timeout=_REQUEST_TIMEOUT_S,
            ),
        )
        self._model = model
        # opus-5/sonnet-5 use extended thinking by default; max_tokens caps
        # thinking + output. Too small a budget (e.g., 4096, or 16000 under the
        # bigger --assist candidates prompts) is exhausted by thinking before
        # the structured response, leaving parsed_output=None. 24000 gives ample
        # room for reasoning plus the JSON guess.
        self._max_tokens = max_tokens

    def next_guess(self, prompt: str) -> GuessResponse:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_format=GuessResponse,
        )
        if response.parsed_output is None:
            raise NoStructuredOutput("Claude returned no structured output")
        return response.parsed_output
