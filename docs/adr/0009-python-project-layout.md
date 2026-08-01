---
status: Accepted
date: "2026-08-01"
topic: python-project-layout
tags: [language, python, structure]
supersedes: []
related: [python-toolchain, i18n-in-python]
---
# 9. Structure Python projects with pyproject and a src layout

## Context

Python offers many ways to lay out and package a project, and inconsistent choices make
repositories harder to move between. We want one predictable structure, isolated
dependencies, and imports that exercise the installed package rather than the working
directory.

## Decision

- **`pyproject.toml`** is the single source of project metadata and tool configuration
  (PEP 621), built with **hatchling**.
- **`src/` layout** — the importable package lives under `src/<package>/`, so tests run
  against the installed package and can't accidentally import from the checkout root.
- **Virtual environment** per project (`python -m venv .venv`); the package is installed
  editable for development (`pip install -e '.[dev]'`).
- **Python version** is pinned with `requires-python` to a currently-supported release
  (>= 3.12 unless the project states otherwise).
- Console entry points are declared under `[project.scripts]`.

## Alternatives considered

- **Flat layout (package at repo root)** — rejected because it lets tests silently import
  from the working directory instead of the installed package, hiding packaging bugs.
- **setup.py / setup.cfg** — rejected in favor of `pyproject.toml`; PEP 621 metadata avoids
  executable build scripts and keeps all tool config in one file.
- **Poetry or PDM for env/dependency management** — rejected in favor of stdlib `venv` plus
  editable installs, keeping the toolchain to one dependency-free, universally available tool.

## Consequences

- Every Python repo is laid out the same way, so setup and navigation are predictable.
- The src layout catches "works on my machine" import bugs before they ship.
- Contributors must install the package (editable) before imports resolve — a one-time
  step documented in the README.
