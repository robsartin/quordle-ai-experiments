---
status: Accepted
date: "2026-08-01"
topic: llm-backed-policy-and-providers
tags: [architecture, solver, llm, provider]
supersedes: []
related: [pluggable-policy-and-objective, solver-environment-separation]
---
# 17. Let LLMs play as a policy, behind a provider abstraction

## Context

A core goal is to have LLMs — Claude first, Gemini soon — play Quordle, and to
compare them against the heuristic solver, against each other, and across different
levels of engine assistance. This must reuse the existing engine, solver loop, logging,
and objective metrics rather than growing a parallel "LLM plays the game" code path.

## Decision

- **An LLM player is a `Policy`.** `LLMPolicy` implements the same
  `Policy.choose(boards, allowed, remaining) -> guess` interface as the heuristic
  ([ADR 15](0015-pluggable-policy-and-objective.md)). It renders the observable game
  state into a prompt, asks a model for the next guess, and returns it to the unchanged
  solver loop and `SimEngine` ([ADR 13](0013-solver-environment-separation.md)).
- **Providers are abstracted.** A narrow `LLMProvider` interface
  (`next_guess(prompt) -> structured result`) has one implementation per model:
  - **Claude** via the official `anthropic` SDK, default model `claude-opus-5`, using
    **structured outputs** so the guess comes back as a validated field, not prose.
  - **Gemini** via Google's own `google-genai` SDK and its native structured output.
  Each lives in its own module. We do **not** route Gemini through an OpenAI-compatible
  shim or the Anthropic SDK — each provider uses its own official SDK.
- **Assist level is a parameter** of `LLMPolicy`: `none` (pure — the model sees only
  what a human sees), `constraints` (the engine supplies derived per-board constraints),
  or `candidates` (the engine supplies the remaining candidate list). Default is `none`;
  the level is an experiment axis reported alongside the objective metrics.
- **Invalid guesses are re-prompted, then fall back.** A guess that is not a valid word
  is re-prompted up to a small fixed number of times with the reason; on exhaustion the
  policy submits a deterministic valid fallback and flags it in the game record. (A guess
  that merely contradicts prior feedback is a legal, if poor, Quordle move and is kept.)

## Alternatives considered

- **A bespoke LLM game loop outside the `Policy` interface** — rejected: duplicates the
  solver, and loses reuse of logging, metrics, and the environment seam.
- **A provider-neutral shim / OpenAI-compatible layer for all models** — rejected: it
  forfeits each SDK's native structured-output support and blurs provider-specific
  behavior we actually want to study.

## Consequences

- LLM play adds API keys, per-guess latency, cost, and non-determinism; each game record
  logs the model, assist level, and token usage so runs are interpretable.
- The `LLMProvider` interface admits a **scripted mock provider**, so `LLMPolicy` is
  unit-testable with no network and CI stays offline ([ADR 2](0002-use-test-driven-development.md)).
- "Model vs. model", "model vs. heuristic", and "pure vs. assisted" all become the same
  kind of comparison the objective harness already runs.
