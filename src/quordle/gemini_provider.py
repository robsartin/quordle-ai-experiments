"""Gemini behind the LLMProvider interface (ADR 17): Google's official
google-genai SDK with native structured output. A separate module from
provider.py -- no cross-provider shim, per ADR 17."""

from quordle.provider import _REQUEST_TIMEOUT_S, GuessResponse, NoStructuredOutput


class GeminiProvider:
    """Gemini via the official google-genai SDK, native structured output,
    default gemini-3.5-flash."""

    def __init__(self, model: str = "gemini-3.5-flash") -> None:
        from google import genai
        from google.genai import types

        # 150s read backstop mirrors ClaudeProvider (_REQUEST_TIMEOUT_S): well
        # above a real thinking call, well below a wedged-socket stall, so the
        # runner's transient-skip path can catch a true stall in bounded time.
        # HttpOptions.timeout is in milliseconds. The SDK reads GEMINI_API_KEY
        # from the env; construction makes no network call.
        self._client = genai.Client(
            http_options=types.HttpOptions(timeout=int(_REQUEST_TIMEOUT_S * 1000))
        )
        self._model = model

    def next_guess(self, prompt: str) -> GuessResponse:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GuessResponse,
            ),
        )
        # isinstance both narrows for strict mypy and covers None / a non-model
        # payload -- either way there is no usable structured guess.
        parsed = response.parsed
        if not isinstance(parsed, GuessResponse):
            raise NoStructuredOutput("Gemini returned no structured output")
        return parsed
