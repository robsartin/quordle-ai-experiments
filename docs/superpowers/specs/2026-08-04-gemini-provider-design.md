# Gemini provider (google-genai) behind LLMProvider

- **Issue:** #5 (Phase 2)
- **Date:** 2026-08-04
- **Depends on / implements:** [ADR 0017](../../adr/0017-llm-backed-policy-and-providers.md)

## Goal

Let Gemini play Quordle as an `LLMPolicy`, exactly like Claude, so
model-vs-model and model-vs-heuristic comparisons run through the same
solver loop, logging, and objective harness. Add a `GeminiProvider` using
Google's own `google-genai` SDK and its native structured output, wire it
into the runner CLI (`--player gemini`), and give Gemini models compact
codes in the objective harness. No cross-provider shim: each provider uses
its own official SDK, per ADR 0017.

## Non-goals

- No `python-dotenv` / `.env` loading. The SDK reads `GEMINI_API_KEY` from
  the real environment, matching how the Anthropic key is handled
  (exported in `~/.zshrc`).
- No refactor of the existing `provider.py` layout. `ClaudeProvider` and
  the shared pieces stay put; `GeminiProvider` is a new sibling module.
- No IPv4-bind workaround up front (see Error handling).

## Components

### 1. `src/quordle/gemini_provider.py` (new)

`GeminiProvider` satisfies the `LLMProvider` protocol structurally and
reuses the shared pieces from `provider.py` — `GuessResponse` and
`NoStructuredOutput`. It does **not** subclass `ClaudeProvider` or share a
client.

```python
class GeminiProvider:
    """Gemini via Google's official google-genai SDK, native structured
    output, default gemini-2.5-flash."""

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        from google import genai
        from google.genai import types

        # 150s read backstop, mirroring ClaudeProvider: enough for a real
        # thinking call, well under a wedged-socket stall, so the runner's
        # transient-skip path can catch a true stall in bounded time.
        # http_options.timeout is in milliseconds.
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
        parsed = response.parsed
        if parsed is None:
            raise NoStructuredOutput("Gemini returned no structured output")
        return parsed  # a validated GuessResponse
```

- **Constructor is offline.** `genai.Client()` sets up the client and reads
  `GEMINI_API_KEY` from the env; it makes no network call. (If the SDK
  requires a key present at construction, tests inject a dummy one — see
  Testing.)
- `_REQUEST_TIMEOUT_S` (150.0) is imported from `provider.py` rather than
  redefined, so the two providers keep the same bound.
- Default model **`gemini-2.5-flash`**.

### 2. Dependency

Add `google-genai>=1.0` to `pyproject.toml` `dependencies` and install it
into the env. `mypy` runs bare (src only), so no test-side typing concerns.

### 3. Runner wiring (`src/quordle/runner.py`)

- `--player` choices gain `"gemini"` → `["heuristic", "claude", "gemini"]`.
- `--model` **default becomes `None`** (was the claude-specific
  `"claude-opus-5"`). `build_policy_factory` resolves a per-player default
  when `model is None`:
  - `claude` → `"claude-sonnet-5"`
  - `gemini` → `"gemini-2.5-flash"`
  - `heuristic` → model is irrelevant (unchanged).

  So `--player gemini` alone works, and the **resolved** model is what lands
  in metadata (never a `None` or a wrong-provider default).
- New `gemini` branch in `build_policy_factory`:

  ```python
  if player == "gemini":
      assist_level = Assist(assist)
      resolved = model or "gemini-2.5-flash"

      def gemini_factory() -> Policy:
          return LLMPolicy(GeminiProvider(model=resolved), assist=assist_level, openers=openers)

      return gemini_factory, {
          "player": "gemini",
          "model": resolved,
          "assist": assist,
          "mode": "gemini",
          "openers": fixed_openers,
      }
  ```

  Assist levels (`none` / `constraints` / `candidates`) come free via
  `LLMPolicy`; nothing Gemini-specific is needed for them.
- `ClaudeProvider`'s own default model changes to `"claude-sonnet-5"` so the
  provider and the resolved CLI default agree. The `max_tokens=24000`
  comment is updated to name sonnet-5 (both opus-5 and sonnet-5 think by
  default, so the budget rationale is unchanged).

### 4. Objective short codes (`src/quordle/objectives.py`)

Extend `_BASE_CODE` so each model has a distinct lowercase base letter;
the existing "uppercase iff `candidates` assist" rule then yields the
assisted variant for free. This also fixes a latent bug: `claude-opus-5` is
currently unmapped and falls back to the player initial `c`, colliding with
`claude-sonnet-5`.

```python
_BASE_CODE = {
    ("heuristic", "-"): "h",
    ("claude", "claude-sonnet-5"): "c",   # C = + candidates
    ("claude", "claude-opus-5"): "o",     # O = + candidates
    ("gemini", "gemini-2.5-flash"): "g",  # G = + candidates
    ("gemini", "gemini-2.5-flash-lite"): "f",  # F
    ("gemini", "gemini-2.5-pro"): "p",    # P
}
```

Final map (base / +candidates), suffix = fixed-opener count:

| player · model | base | + candidates |
|---|---|---|
| heuristic | `h` | — |
| claude sonnet-5 | `c` | `C` |
| claude opus-5 | `o` | `O` |
| gemini 2.5-flash | `g` | `G` |
| gemini 2.5-flash-lite | `f` | `F` |
| gemini 2.5-pro | `p` | `P` |

### 5. Security (`.gitignore`)

Add `.env` so a key file (one appeared untracked this session) can never be
committed. The key itself lives in `~/.zshrc` as `GEMINI_API_KEY`; the
provider reads it from the env via the SDK. The key is never read, printed,
or written by our code.

## Data flow

`runner --player gemini` → `build_policy_factory` → `LLMPolicy(GeminiProvider,
assist, openers)` → unchanged `solve()` / `SimEngine` loop → each guess:
`LLMPolicy` renders board state to a prompt → `GeminiProvider.next_guess` →
`generate_content(response_schema=GuessResponse)` → validated `GuessResponse`
→ solver submits guess. Games logged to JSONL exactly as Claude's, tagged
`player=gemini`, `model`, `assist`, `openers`; the objective harness groups
by `(player, model, assist, openers)` and renders the compact code in CSV.

## Error handling

- **No structured output** → raise `NoStructuredOutput` (shared type). The
  runner already treats it as a skippable per-game failure in both the sim
  (`run_many`) and browser loops.
- **Transient-skip parity.** Today the sim/browser loops catch
  `anthropic.APIConnectionError` + `NoStructuredOutput` so a single stall
  skips one game instead of killing a multi-hour sweep. This is broadened to
  also catch Gemini's transient failures (request timeout and 5xx server
  errors) via the `google-genai` error types. Auth / 4xx / bad-request
  errors still propagate loudly — those are real bugs, not stalls. The exact
  exception classes (`google.genai.errors.ServerError`, the SDK's timeout
  type) are pinned during TDD once the SDK is installed; the caught set is
  the union across providers, kept in the existing `except` clauses.
- **No IPv4 bind.** The `local_address="0.0.0.0"` trick was a fix for an
  Anthropic-specific wedged-IPv6 stall. Gemini gets the timeout backstop
  only; the IPv4 bind is added later *only if* Gemini exhibits the same
  stall. (YAGNI.)

## Testing

`tests/test_gemini_provider.py`, mirroring `tests/test_provider.py`. All
offline unit tests inject a dummy key first:
`monkeypatch.setenv("GEMINI_API_KEY", "test-key")` before constructing, so
construction never depends on a real key or the network.

- `test_gemini_provider_default_model_is_flash` — offline ctor, `_model ==
  "gemini-2.5-flash"`.
- `test_gemini_provider_raises_no_structured_output_on_unparseable` —
  monkeypatch `provider._client.models.generate_content` to return an object
  whose `.parsed is None`; assert `NoStructuredOutput`.
- `test_gemini_provider_read_timeout_is_bounded` — assert the client's
  configured HTTP timeout equals `_REQUEST_TIMEOUT_S` (150s, in ms), reading
  it back from the client without coupling to deep SDK internals where
  possible.
- `test_gemini_provider_returns_a_five_letter_word` — live, gated behind
  `@pytest.mark.skipif(os.getenv("RUN_LLM_TESTS") != "1", ...)`, same as the
  Claude live test.

`tests/test_provider.py`:
- Add `test_claude_provider_default_model_is_sonnet` — `ClaudeProvider()._model
  == "claude-sonnet-5"`.

`tests/test_objectives.py`:
- `_short_label` cases for opus `o`/`O`, flash `g`/`G`, flash-lite `f`/`F`,
  pro `p`/`P`, each with and without an opener digit.
- Regression: `claude-opus-5` no longer collides with `claude-sonnet-5`.

`tests/test_runner.py`:
- `build_policy_factory("gemini", "none", None, k)` returns an `LLMPolicy`
  wrapping a `GeminiProvider`, with metadata `player=gemini`,
  `model=gemini-2.5-flash`, `openers=k`.
- `build_policy_factory("claude", "none", None, k)` resolves
  `model=claude-sonnet-5` (the new per-player default).
- Constructing the gemini factory injects a dummy `GEMINI_API_KEY` so the
  `GeminiProvider` builds offline.

CI stays fully offline (no live LLM tests); coverage floor line >80% /
branch >65% must hold.

## Build sequence (TDD, red → green per step)

1. Add `google-genai` dep; install.
2. `GeminiProvider` — default model, structured `next_guess`,
   `NoStructuredOutput` path, bounded timeout. (test_gemini_provider.py)
3. `ClaudeProvider` default → sonnet-5. (test_provider.py)
4. `_BASE_CODE` additions + collision regression. (test_objectives.py)
5. Runner: `--player gemini`, `--model` default None + per-player
   resolution, gemini branch. (test_runner.py)
6. Transient-skip parity for Gemini errors in the sim/browser loops.
7. `.gitignore` `.env`.
8. Full CI gate: `ruff format --check`, `ruff check`, `mypy`, `pytest
   --cov`. PR → squash-merge.
