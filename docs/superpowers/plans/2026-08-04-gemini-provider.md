# Gemini Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Gemini play Quordle as an `LLMPolicy` via Google's `google-genai` SDK, wired into the runner (`--player gemini`) and the objective harness, so model-vs-model and model-vs-heuristic comparisons run through the existing solver/logging/metrics.

**Architecture:** A new `GeminiProvider` module satisfies the existing `LLMProvider` protocol structurally, reusing `GuessResponse` / `NoStructuredOutput` / `_REQUEST_TIMEOUT_S` from `provider.py`. No cross-provider shim (ADR 0017): each provider uses its own official SDK with native structured output. The runner gains a `gemini` branch and per-player `--model` default resolution; the objective harness gains compact codes for the new models; the sim/browser loops broaden their transient-skip to include Gemini's transient errors.

**Tech Stack:** Python 3.14 (pinned via `.python-version`), `google-genai>=1.0`, `pydantic>=2`, `anthropic`, `httpx`, pytest + pytest-cov, ruff, mypy (strict).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-04-gemini-provider-design.md` (ADR 0017).
- **CI gate — all must pass before push:** `ruff format --check .`, `ruff check .`, `mypy` (bare; checks `src` only via `packages=["quordle"]`), `pytest --cov=quordle --cov-branch --cov-report=term-missing`. Tools at `~/.pyenv/versions/3.14.3/bin/`.
- **mypy is `strict = true`** — all new src code fully typed; `isinstance` narrowing is used to satisfy `warn_return_any` on `response.parsed`.
- **Coverage floors:** line > 80%, branch > 65%.
- **TDD:** red → green per step; failing test runs before the implementation exists.
- **Staging:** `git add` **by explicit path** only (never `git add -A`).
- **Secrets:** the SDK reads `GEMINI_API_KEY` from the env; our code never reads, prints, or writes the key. Offline tests inject a dummy key via `monkeypatch.setenv` (the ctor raises `ValueError` without one).
- **Default models:** claude → `claude-sonnet-5`; gemini → `gemini-2.5-flash`.
- **Short-code map (base / +candidates):** heuristic `h`; sonnet-5 `c`/`C`; opus-5 `o`/`O`; flash `g`/`G`; flash-lite `f`/`F`; pro `p`/`P`. Suffix = fixed-opener count (omitted when openers is `None`).
- **Branch:** `5-gemini-provider` (already created; spec already committed on it).

---

### Task 1: GeminiProvider module (+ dependency, + `.env` gitignore)

**Files:**
- Create: `src/quordle/gemini_provider.py`
- Create: `tests/test_gemini_provider.py`
- Modify: `pyproject.toml` (add `google-genai>=1.0` to `dependencies`)
- Modify: `.gitignore` (add `.env`)

**Interfaces:**
- Consumes: `GuessResponse`, `NoStructuredOutput`, `_REQUEST_TIMEOUT_S` from `quordle.provider`.
- Produces: `GeminiProvider(model: str = "gemini-2.5-flash")` with `.next_guess(prompt: str) -> GuessResponse` and attributes `_client`, `_model`. Satisfies the `LLMProvider` protocol structurally.

- [ ] **Step 1: Add the dependency and install**

Edit `pyproject.toml` `dependencies` (currently lines ~11-16) to add the SDK:

```toml
dependencies = [
    "matplotlib>=3.5",
    "anthropic>=0.40",
    "google-genai>=1.0",
    "pydantic>=2",
    "playwright>=1.40",
]
```

Then install into the pinned interpreter:

Run: `~/.pyenv/versions/3.14.3/bin/pip install -e ".[dev]"`
Expected: installs `google-genai` (already present in this env at 2.16.0; command is idempotent).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_gemini_provider.py`:

```python
import os

import pytest

from quordle.provider import NoStructuredOutput


def test_gemini_provider_default_model_is_flash(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # ctor needs a key present
    from quordle.gemini_provider import GeminiProvider

    assert GeminiProvider()._model == "gemini-2.5-flash"


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_gemini_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quordle.gemini_provider'`.

- [ ] **Step 4: Write the minimal implementation**

Create `src/quordle/gemini_provider.py`:

```python
"""Gemini behind the LLMProvider interface (ADR 17): Google's official
google-genai SDK with native structured output. A separate module from
provider.py -- no cross-provider shim, per ADR 17."""

from quordle.provider import GuessResponse, NoStructuredOutput, _REQUEST_TIMEOUT_S


class GeminiProvider:
    """Gemini via the official google-genai SDK, native structured output,
    default gemini-2.5-flash."""

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_gemini_provider.py -v`
Expected: PASS for the 3 offline tests; the live test is SKIPPED (no `RUN_LLM_TESTS`).

- [ ] **Step 6: Add `.env` to `.gitignore`**

Add under the "Local scratch" section of `.gitignore`:

```
# API key files -- keys live in ~/.zshrc; never commit one
.env
```

- [ ] **Step 7: Run the full gate**

Run: `~/.pyenv/versions/3.14.3/bin/ruff format --check . && ~/.pyenv/versions/3.14.3/bin/ruff check . && ~/.pyenv/versions/3.14.3/bin/mypy && ~/.pyenv/versions/3.14.3/bin/pytest --cov=quordle --cov-branch --cov-report=term-missing`
Expected: all green. (If `ruff format --check` flags the new file, run `ruff format .` and re-check.)

- [ ] **Step 8: Commit**

```bash
git add src/quordle/gemini_provider.py tests/test_gemini_provider.py pyproject.toml .gitignore
git commit -m "feat: GeminiProvider via google-genai behind LLMProvider (#5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: ClaudeProvider default → claude-sonnet-5

**Files:**
- Modify: `src/quordle/provider.py:47-50` (docstring + default arg)
- Modify: `tests/test_provider.py` (add default-model test)

**Interfaces:**
- Produces: `ClaudeProvider(model: str = "claude-sonnet-5")` — default changes from `claude-opus-5`. `.next_guess` unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_provider.py`:

```python
def test_claude_provider_default_model_is_sonnet():
    from quordle.provider import ClaudeProvider

    # Default flipped to sonnet-5 (issue #5): the everyday comparison model,
    # matching the runner's per-player default. Constructed offline (no key
    # needed at construction for the anthropic SDK).
    assert ClaudeProvider()._model == "claude-sonnet-5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_provider.py::test_claude_provider_default_model_is_sonnet -v`
Expected: FAIL — `assert 'claude-opus-5' == 'claude-sonnet-5'`.

- [ ] **Step 3: Change the default**

In `src/quordle/provider.py`, update the docstring (line ~48) and default (line ~50):

```python
class ClaudeProvider:
    """Claude via the official anthropic SDK, structured outputs, default claude-sonnet-5."""

    def __init__(self, model: str = "claude-sonnet-5", max_tokens: int = 24000) -> None:
```

Leave the `max_tokens` comment as-is: it already notes "opus-5/sonnet-5 use extended thinking by default", which stays true.

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_provider.py -v`
Expected: PASS (new test green; existing provider tests unaffected — none assert the old default).

- [ ] **Step 5: Commit**

```bash
git add src/quordle/provider.py tests/test_provider.py
git commit -m "feat: default ClaudeProvider model to claude-sonnet-5 (#5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Objective short codes for opus + Gemini models

**Files:**
- Modify: `src/quordle/objectives.py:73-82` (`_BASE_CODE` + comment)
- Modify: `tests/test_objectives.py` (add short-code tests)

**Interfaces:**
- Consumes: existing `_short_label(player, model, assist, openers) -> str` and its "uppercase iff `candidates`" rule (unchanged).
- Produces: `_BASE_CODE` mapping opus-5→`o`, flash→`g`, flash-lite→`f`, pro→`p` (sonnet-5→`c` and heuristic→`h` unchanged).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_objectives.py` (under the existing "short config codes (CSV)" section):

```python
def test_short_label_maps_opus_and_gemini_models():
    from quordle.objectives import _short_label

    assert _short_label("claude", "claude-opus-5", "none", 0) == "o0"
    assert _short_label("claude", "claude-opus-5", "candidates", 0) == "O0"
    assert _short_label("gemini", "gemini-2.5-flash", "none", 1) == "g1"
    assert _short_label("gemini", "gemini-2.5-flash", "candidates", 1) == "G1"
    assert _short_label("gemini", "gemini-2.5-flash-lite", "none", None) == "f"
    assert _short_label("gemini", "gemini-2.5-flash-lite", "candidates", 2) == "F2"
    assert _short_label("gemini", "gemini-2.5-pro", "none", 3) == "p3"
    assert _short_label("gemini", "gemini-2.5-pro", "candidates", 3) == "P3"


def test_short_label_opus_no_longer_collides_with_sonnet():
    from quordle.objectives import _short_label

    # Before this task opus-5 was unmapped and fell back to the player initial
    # "c", colliding with sonnet-5. Explicit "o" separates them.
    assert _short_label("claude", "claude-sonnet-5", "none", 0) == "c0"
    assert _short_label("claude", "claude-opus-5", "none", 0) == "o0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_objectives.py -k "opus or gemini or collide" -v`
Expected: FAIL — opus/gemini map to fallback letters (`c`, `g`, ...) so opus cases return `c0`/`C0`, not `o0`/`O0`.

- [ ] **Step 3: Extend `_BASE_CODE`**

In `src/quordle/objectives.py`, replace the `_BASE_CODE` block (and its comment):

```python
# Compact per-config codes for CSV output: a lowercase base letter identifies
# the player/model, uppercased when the candidates assist is on, then the
# fixed-opener count. Extend _BASE_CODE as more models are added.
#   h        heuristic
#   c / C    claude sonnet-5   (base / + candidates)
#   o / O    claude opus-5
#   g / G    gemini 2.5-flash
#   f / F    gemini 2.5-flash-lite
#   p / P    gemini 2.5-pro
_BASE_CODE: dict[tuple[str, str], str] = {
    ("heuristic", "-"): "h",
    ("claude", "claude-sonnet-5"): "c",
    ("claude", "claude-opus-5"): "o",
    ("gemini", "gemini-2.5-flash"): "g",
    ("gemini", "gemini-2.5-flash-lite"): "f",
    ("gemini", "gemini-2.5-pro"): "p",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_objectives.py -v`
Expected: PASS (new + existing objective tests green).

- [ ] **Step 5: Commit**

```bash
git add src/quordle/objectives.py tests/test_objectives.py
git commit -m "feat: short codes for opus + gemini models, fix opus/sonnet collision (#5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Runner wiring — `--player gemini` + `--model` default resolution

**Files:**
- Modify: `src/quordle/runner.py` — top import; `build_policy_factory` (lines ~166-189); `build_arg_parser` (`--player`, `--model` lines ~435-437)
- Modify: `tests/test_runner.py` (add gemini + default-resolution tests)

**Interfaces:**
- Consumes: `GeminiProvider` from `quordle.gemini_provider` (Task 1); `LLMPolicy` (`.provider` public attr); `ClaudeProvider` default sonnet-5 (Task 2).
- Produces: `build_policy_factory(player, assist, model, fixed_openers)` accepts `model: str | None`; resolves per-player default when `None` (claude→`claude-sonnet-5`, gemini→`gemini-2.5-flash`); a `gemini` branch returning `(factory, metadata)` with metadata keys `player, model, assist, mode, openers`. `--player` choices include `gemini`; `--model` argparse default is `None`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py`:

```python
def test_build_policy_factory_gemini_metadata_and_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # GeminiProvider ctor needs a key
    from quordle.gemini_provider import GeminiProvider
    from quordle.llm_policy import LLMPolicy
    from quordle.runner import build_policy_factory

    factory, metadata = build_policy_factory("gemini", "none", None, 2)
    assert metadata == {
        "player": "gemini",
        "model": "gemini-2.5-flash",
        "assist": "none",
        "mode": "gemini",
        "openers": 2,
    }
    policy = factory()
    assert isinstance(policy, LLMPolicy)
    assert isinstance(policy.provider, GeminiProvider)


def test_build_policy_factory_claude_default_model_is_sonnet():
    from quordle.provider import ClaudeProvider
    from quordle.runner import build_policy_factory

    # model=None now resolves to the per-player default; claude -> sonnet-5.
    factory, metadata = build_policy_factory("claude", "none", None, 2)
    assert metadata["model"] == "claude-sonnet-5"
    assert isinstance(factory().provider, ClaudeProvider)  # ctor offline, no key


def test_arg_parser_includes_gemini_and_model_default_none():
    from quordle.runner import build_arg_parser

    args = build_arg_parser().parse_args(["--player", "gemini"])
    assert args.player == "gemini"
    assert args.model is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py -k "gemini or default_model_is_sonnet or model_default_none" -v`
Expected: FAIL — `build_policy_factory("gemini", ...)` raises `ValueError: unknown player: 'gemini'`; `--player gemini` errors as an invalid choice; `args.model` defaults to `"claude-opus-5"`.

- [ ] **Step 3: Add the import**

In `src/quordle/runner.py`, add near the other provider import (line ~18):

```python
from quordle.gemini_provider import GeminiProvider
```

(The `GeminiProvider` ctor lazy-imports `google.genai`, so this top-level import stays cheap.)

- [ ] **Step 4: Rework `build_policy_factory` for resolution + gemini**

Replace the `build_policy_factory` body (lines ~166-189). Signature gains `| None` on `model`:

```python
def build_policy_factory(
    player: str, assist: str, model: str | None, fixed_openers: int
) -> tuple[Callable[[], Policy], dict[str, Any]]:
    openers = OPENERS[:fixed_openers]
    if player == "heuristic":

        def heuristic_factory() -> Policy:
            return FixedOpenersThenGreedy(list(openers))

        return heuristic_factory, {"player": "heuristic", "openers": fixed_openers}
    if player == "claude":
        assist_level = Assist(assist)
        resolved = model or "claude-sonnet-5"

        def claude_factory() -> Policy:
            return LLMPolicy(ClaudeProvider(model=resolved), assist=assist_level, openers=openers)

        return claude_factory, {
            "player": "claude",
            "model": resolved,
            "assist": assist,
            "mode": "claude",
            "openers": fixed_openers,
        }
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
    raise ValueError(f"unknown player: {player!r}")
```

- [ ] **Step 5: Update the arg parser**

In `build_arg_parser` (lines ~435-437):

```python
    parser.add_argument("--player", choices=["heuristic", "claude", "gemini"], default="heuristic")
    parser.add_argument("--assist", choices=["none", "constraints", "candidates"], default="none")
    parser.add_argument("--model", default=None, help="model id; defaults per player "
                        "(claude: claude-sonnet-5, gemini: gemini-2.5-flash)")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py -v`
Expected: PASS. Existing `build_policy_factory` tests still pass — they pass an explicit `model`, which `model or default` leaves untouched.

- [ ] **Step 7: Commit**

```bash
git add src/quordle/runner.py tests/test_runner.py
git commit -m "feat: --player gemini and per-player --model default resolution (#5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Transient-skip parity for Gemini errors

**Files:**
- Modify: `src/quordle/runner.py` — add `_transient_error_types()` helper; use it in `run_many` (lines ~115, ~131) and `_play_browser_game` (lines ~223, ~245)
- Modify: `tests/test_runner.py` (add ServerError-skip + ClientError-reraise tests)

**Interfaces:**
- Produces: `_transient_error_types() -> tuple[type[BaseException], ...]` = `(anthropic.APIConnectionError, NoStructuredOutput, google.genai.errors.ServerError, httpx.TransportError)`. Used as the `except` tuple in both loops. `ClientError` (4xx) is deliberately excluded so auth/bad-request fails loudly.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py` (top-of-file imports `from quordle import wordlist` and `from quordle.runner import run_many` — reuse the existing module import style already in the file):

```python
def test_run_many_skips_game_on_gemini_server_error():
    from google.genai import errors as genai_errors

    from quordle import wordlist
    from quordle.runner import run_many

    class _BoomPolicy:
        def choose(self, *args, **kwargs):
            raise genai_errors.ServerError(503, {"error": {"message": "overloaded"}})

    records = run_many(
        1,
        seed=0,
        policy_factory=lambda: _BoomPolicy(),
        answers=wordlist.load_answers(),
        allowed=wordlist.load_allowed(),
        start_seq=1,
        date="2026-08-04",
    )
    assert records == []  # transient 5xx -> game skipped, batch survives


def test_run_many_reraises_on_gemini_client_error():
    import pytest
    from google.genai import errors as genai_errors

    from quordle import wordlist
    from quordle.runner import run_many

    class _AuthBoom:
        def choose(self, *args, **kwargs):
            raise genai_errors.ClientError(400, {"error": {"message": "bad key"}})

    with pytest.raises(genai_errors.ClientError):  # 4xx must fail loudly, not skip
        run_many(
            1,
            seed=0,
            policy_factory=lambda: _AuthBoom(),
            answers=wordlist.load_answers(),
            allowed=wordlist.load_allowed(),
            start_seq=1,
            date="2026-08-04",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py -k "gemini_server_error or gemini_client_error" -v`
Expected: FAIL — `ServerError` is not in the current `(APIConnectionError, NoStructuredOutput)` catch, so `run_many` propagates it instead of returning `[]`.

- [ ] **Step 3: Add the helper**

In `src/quordle/runner.py`, add a module-level helper (near the top, after the constants around line ~22):

```python
def _transient_error_types() -> tuple[type[BaseException], ...]:
    """Per-call failures a multi-game sweep should skip (not crash on): a
    provider connection/timeout stall and no-structured-output. Auth / 4xx /
    bad-request errors (anthropic.APIStatusError, google.genai ClientError) are
    deliberately NOT included -- those are real bugs that must fail loudly
    rather than silently skip every game. Imported lazily to keep module import
    light, matching the existing per-loop import style."""
    import httpx
    from anthropic import APIConnectionError
    from google.genai import errors as genai_errors

    return (APIConnectionError, NoStructuredOutput, genai_errors.ServerError, httpx.TransportError)
```

- [ ] **Step 4: Use the helper in `run_many`**

In `run_many`, remove the local `from anthropic import APIConnectionError` (line ~115) and change the `except` (line ~131) to:

```python
        except _transient_error_types() as exc:
            print(f"Sim game {seq} interrupted by a transient API error ({exc!r}); skipping.")
            continue
```

- [ ] **Step 5: Use the helper in `_play_browser_game`**

In `_play_browser_game`, remove its local `from anthropic import APIConnectionError` (line ~223, keep the `from quordle.browser.browser_env import GuessRejected` import) and change the `except` (line ~245) to:

```python
            except _transient_error_types() as exc:
                return SolveResult(guesses, solved_on), exc
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `~/.pyenv/versions/3.14.3/bin/pytest tests/test_runner.py -v`
Expected: PASS. The existing transient tests (`...transient_api_error`, `...no_structured_output`, `...ends_gracefully_on_api_timeout`, `...on_no_structured_output`) still pass — `APIConnectionError` and `NoStructuredOutput` remain in the tuple.

- [ ] **Step 7: Commit**

```bash
git add src/quordle/runner.py tests/test_runner.py
git commit -m "feat: skip Gemini transient (5xx/timeout) errors in sweeps, keep 4xx loud (#5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Final verification & PR

- [ ] **Step 1: Run the complete CI gate (the merge gate)**

Run: `~/.pyenv/versions/3.14.3/bin/ruff format --check . && ~/.pyenv/versions/3.14.3/bin/ruff check . && ~/.pyenv/versions/3.14.3/bin/mypy && ~/.pyenv/versions/3.14.3/bin/pytest --cov=quordle --cov-branch --cov-report=term-missing`
Expected: all four green; coverage line > 80%, branch > 65%.

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin 5-gemini-provider
gh pr create --fill --base main
```

PR body should note: implements #5 / ADR 0017; adds `GeminiProvider` (google-genai, default gemini-2.5-flash), `--player gemini`, per-player `--model` defaults (claude→sonnet-5), objective short codes `o/g/f/p`, `.env` gitignore, and Gemini transient-skip parity. End with the Claude Code attribution line.

- [ ] **Step 3: Report the PR URL and stop for review.** Do not merge — Rob squash-merges after review (never dev on an open non-draft PR).

## Self-Review

**Spec coverage:**
- GeminiProvider module, own SDK, structured output, default flash → Task 1. ✓
- `google-genai` dependency → Task 1. ✓
- `.env` gitignore / key from env → Task 1 + Global Constraints. ✓
- ClaudeProvider default → sonnet-5 → Task 2. ✓
- Objective short codes (o/g/f/p, +candidates, opus collision fix) → Task 3. ✓
- Runner `--player gemini`, `--model` default None + per-player resolution, gemini branch/metadata → Task 4. ✓
- Transient-skip parity (ServerError/timeout skipped, 4xx loud), no IPv4 bind → Task 5 + Task 1 (timeout only). ✓
- Tests mirror `test_provider.py`, offline dummy-key, live gated behind `RUN_LLM_TESTS` → Task 1. ✓

**Placeholder scan:** No TBD/TODO; every code + test block is concrete; commands are exact. ✓

**Type consistency:** `GeminiProvider(model=...)`, `.provider` attr, `_transient_error_types()` tuple, `build_policy_factory(model: str | None)`, metadata keys (`player/model/assist/mode/openers`) are consistent across Tasks 1, 4, 5 and match the existing claude branch. ✓
