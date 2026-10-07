"""Command line: init, fetch, ingest, build, diff. Every command prints one JSON object."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import ParetoError
from .build import build
from .diff import diff
from .fetch import fetch
from .space import Space, as_text
from .table import ingest


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ParetoError(message, "usage", 2)


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", type=Path, default=Path("."), help="project folder that holds .ihav_space/ (default: current folder)")
    root = _Parser(prog="ihav-openrouter-pareto", description="OpenRouter quality or usage vs price, with Pareto frontiers.")
    commands = root.add_subparsers(dest="command", required=True, parser_class=_Parser)
    commands.add_parser("init", parents=[common], help="create .ihav_space/ihav-openrouter-pareto with a default config; never overwrites")
    commands.add_parser("fetch", parents=[common], help="public, key-free GETs of the catalog and typed endpoint prices into a new capture")
    step = commands.add_parser("ingest", parents=[common], help="store Table text read by the skill's browser step")
    step.add_argument("--capture", help="capture id or YYYY-MM-DD (default: newest)")
    step.add_argument("--modality", required=True, help="text, image, speech, another configured modality, or all")
    step.add_argument("--file", required=True, type=Path, help="`|`-separated Table text with a '# Columns:' line")
    step.add_argument("--url", required=True, help="page URL the Table came from")
    step.add_argument("--expected-rows", required=True, type=int, help="row count the page showed")
    step.add_argument("--view", default="table", help="page view mode; only 'table'")
    step.add_argument("--captured-at", help="ISO time the Table was read (default: now)")
    step.add_argument("--columns", help="'|'-separated column names when the text has no '# Columns:' line")
    make = commands.add_parser("build", parents=[common], help="normalise a capture, write HTML, CSV and JSON, move latest if valid")
    make.add_argument("--capture", help="capture id or YYYY-MM-DD (default: newest)")
    compare = commands.add_parser("diff", parents=[common], help="changes between two captures")
    compare.add_argument("a", help="capture id or unambiguous YYYY-MM-DD")
    compare.add_argument("b", help="capture id or unambiguous YYYY-MM-DD")
    return root


def run(args: argparse.Namespace) -> tuple[dict, int]:
    space = Space(args.project)
    if args.command == "init":
        return {"space": str(space.root), "created": space.init()}, 0
    if args.command == "fetch":
        return fetch(space), 0
    if args.command == "ingest":
        columns = [c.strip() for c in args.columns.split("|")] if args.columns else None
        result = ingest(space, args.capture, args.modality, args.file, args.url, args.expected_rows, args.view, args.captured_at, columns)
        return result, 0 if result["complete"] else 3
    if args.command == "build":
        result = build(space, args.capture)
        return result, 0 if result["validated"] else 3
    return diff(space, args.a, args.b), 0


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result, code = run(parser().parse_args(argv))
    except ParetoError as exc:
        result, code = {"error": {"code": exc.code, "message": str(exc)}}, exc.exit_code
    print(json.dumps(result, ensure_ascii=False, indent=1, default=as_text))
    return code
