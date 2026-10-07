#!/usr/bin/env python3
"""Portable entry point for Claude Code, Codex and direct terminal use."""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 9):
    print("ihav-openrouter-pareto requires Python 3.9 or later.", file=sys.stderr)
    raise SystemExit(64)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ihav_openrouter_pareto.cli import configure_stdio, main  # noqa: E402

configure_stdio()

if __name__ == "__main__":
    raise SystemExit(main())
