# Architecture Decision Records

## Universal

- [1. Record architecture decisions with ADRs](0001-record-architecture-decisions.md) — _Accepted_
  Architecturally significant decisions — choices that shape structure, dependencies, interfaces, or the way the team works — need a durable record.
  Related: [6. Keep developer and user documentation current](0006-keep-documentation-current.md)
- [2. Develop with Test-Driven Development](0002-use-test-driven-development.md) — _Accepted_
  We want a fast feedback loop, a regression safety net, executable documentation of behavior, and the freedom to refactor without fear.
- [3. Integrate via a PR-based trunk workflow](0003-pr-based-trunk-workflow.md) — _Accepted_
  We want `main` to stay releasable at all times, changes to be reviewable in coherent units, and history to be legible.
  Related: [4. Use the Mikado Method to keep the build green](0004-mikado-method-for-changes.md), [5. Make CI the merge gate](0005-ci-is-the-merge-gate.md), [6. Keep developer and user documentation current](0006-keep-documentation-current.md)
- [4. Use the Mikado Method to keep the build green](0004-mikado-method-for-changes.md) — _Accepted_
  Large refactorings, and changes that ripple across a codebase, tempt us into long stretches where nothing compiles and nothing is committable.
  Related: [3. Integrate via a PR-based trunk workflow](0003-pr-based-trunk-workflow.md)
- [5. Make CI the merge gate](0005-ci-is-the-merge-gate.md) — _Accepted_
  Standards that are not enforced erode.
  Related: [10. Standardize the Python quality toolchain](0010-python-toolchain.md)
- [6. Keep developer and user documentation current](0006-keep-documentation-current.md) — _Accepted_
  Documentation that lags the code is worse than none — it misleads.
  Related: [1. Record architecture decisions with ADRs](0001-record-architecture-decisions.md), [3. Integrate via a PR-based trunk workflow](0003-pr-based-trunk-workflow.md)
- [7. Declare an explicit license and copyright](0007-license-and-copyright.md) — _Accepted_
  A repository with no license is "all rights reserved" by default — others (and future us) have no clear terms for use, and intent is ambiguous.
- [8. Maintain a security baseline](0008-security-baseline.md) — _Accepted_
  Secrets committed to a repository are effectively public and permanent — history preserves them even after deletion.

## Language

- [9. Structure Python projects with pyproject and a src layout](0009-python-project-layout.md) — _Accepted_
  Python offers many ways to lay out and package a project, and inconsistent choices make repositories harder to move between.
  Related: [10. Standardize the Python quality toolchain](0010-python-toolchain.md)
- [10. Standardize the Python quality toolchain](0010-python-toolchain.md) — _Accepted_
  The universal CI-gate decision requires formatting, tests, and coverage thresholds to be enforced, but leaves the *tools* to each language.
  Related: [9. Structure Python projects with pyproject and a src layout](0009-python-project-layout.md), [5. Make CI the merge gate](0005-ci-is-the-merge-gate.md)

## App shape

- [11. CLI conventions](0011-cli-conventions.md) — _Accepted_
  Command-line tools are used by people at a terminal and by scripts and CI.

## Project-specific

- [12. Evaluate solvers by simulation against a local engine](0012-simulation-first-evaluation.md) — _Accepted_
  Comparing solving strategies across several objectives needs many repeatable games per strategy — the live browser cannot A/B a large fixed sample.
  Related: [13. Separate the solver from the environment](0013-solver-environment-separation.md), [14. Bundle canonical Wordle word lists](0014-bundled-word-lists.md), [15. Pluggable policy and objective](0015-pluggable-policy-and-objective.md)
- [13. Separate the solver from the environment behind a guess interface](0013-solver-environment-separation.md) — _Accepted_
  The simulator now and the browser soon must play the same games; solving logic stays environment-agnostic so it is written and tested once.
  Related: [12. Evaluate solvers by simulation](0012-simulation-first-evaluation.md), [15. Pluggable policy and objective](0015-pluggable-policy-and-objective.md)
- [14. Bundle canonical Wordle word lists as committed data](0014-bundled-word-lists.md) — _Accepted_
  The engine and solver need stable, reproducible answer and allowed-guess lists rather than a brittle scrape or a noisy system dictionary.
  Related: [12. Evaluate solvers by simulation](0012-simulation-first-evaluation.md)
- [15. Make guess-selection policy and optimization objective pluggable](0015-pluggable-policy-and-objective.md) — _Accepted_
  No single strategy wins on every objective, so strategies and objectives vary independently and all metrics are reported for every policy.
  Related: [12. Evaluate solvers by simulation](0012-simulation-first-evaluation.md), [13. Separate the solver from the environment](0013-solver-environment-separation.md)
- [16. Record games as append-only JSONL; render a static HTML dashboard](0016-jsonl-log-and-static-dashboard.md) — _Accepted_
  Records the established log and dashboard format so the new engine, solver, and runner conform to it rather than inventing a parallel format.
  Related: [12. Evaluate solvers by simulation](0012-simulation-first-evaluation.md)
- [17. Let LLMs play as a policy, behind a provider abstraction](0017-llm-backed-policy-and-providers.md) — _Accepted_
  An LLM player is just another policy; Claude (anthropic SDK, claude-opus-5) and Gemini (google-genai) sit behind an LLMProvider interface, with engine-assist level as an experiment axis.
  Related: [15. Pluggable policy and objective](0015-pluggable-policy-and-objective.md), [13. Separate the solver from the environment](0013-solver-environment-separation.md)
- [18. Make Gemini sweeps throttle-robust: bounded SDK retry plus top-up until N completed](0018-throttle-robust-gemini-sweeps.md) — _Accepted_
  Free-tier throttling leaves a fixed-N sweep short; completed games are counted from the log and topped up on fresh, deduplicated puzzles.
  Related: [17. Let LLMs play as a policy, behind a provider abstraction](0017-llm-backed-policy-and-providers.md), [16. Record games as append-only JSONL](0016-jsonl-log-and-static-dashboard.md)
