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


class ClaudeProvider:
    """Claude via the official anthropic SDK, structured outputs, default claude-opus-5."""

    def __init__(self, model: str = "claude-opus-5", max_tokens: int = 4096) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def next_guess(self, prompt: str) -> GuessResponse:
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_format=GuessResponse,
        )
        if response.parsed_output is None:
            raise RuntimeError("Claude returned no structured output")
        return response.parsed_output
