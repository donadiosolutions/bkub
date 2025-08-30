# AGENTS

This repository contains the `bootServer` package and related utilities for serving boot
artifacts over HTTP, HTTPS, and TFTP. Follow these guidelines when modifying the codebase.

## Code conventions
- Target Python **3.13** and enable `from __future__ import annotations` where forward references are used.
- Format Python with **black** (120 character line length) and sort imports with **isort** using the black profile.
- Lint with **flake8** and keep lines at or below 120 characters.
- Provide complete type hints and verify with **pyright** (strict settings).
- Use `logging` for diagnostics and `pathlib.Path` for filesystem paths.
- Tests live under `tests/` and use `pytest` markers (`unit`, `integration`, `slow`). Name files `test_*.py`.
- Shell scripts should use `#!/usr/bin/env bash` and begin with `set -euo pipefail`.

## Required checks
Before committing:
1. Auto-format code: `make format`
2. Lint, type-check, and format-check: `make quality`
3. Run the test suite: `make test`

Ensure all commands pass before creating a commit.

## Project structure
- `bootServer/` – core application modules and CLI entry point.
- `tests/` – test suite; add tests for new functionality.
- `scripts/` – helper shell scripts.
- `boot-artifacts/` – artifacts served by the server (not tracked).

## Commit guidelines
- Make small, focused commits with imperative subject lines.
- Update documentation when behavior or interfaces change.
- Do not commit secrets; gitleaks runs in pre-commit hooks.

These instructions apply to the entire repository.
