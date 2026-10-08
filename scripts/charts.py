#!/usr/bin/env python3
"""One command, no LLM and no browser: OpenRouter Pareto charts for text, image, video, speech and decisions.

Live (default): `init`, enable the modalities in config.json, `fetch` (the public, key-free GETs), `build`.
Weekly Tokens, Latency and Throughput come only from the models Table, which needs a browser, so a live build
marks them `unavailable`; a tab with no API metric (video, decisions) then shows "no chart".
--offline: no network; replays the saved 2026-10-07 catalog, image endpoint and Table captures, then `build`.

Prints one JSON object. Exit codes as the CLI: 0 validated, 3 not validated, 2 usage, 4 network or HTTP failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import fixture_build  # noqa: E402  (also puts the plugin core on sys.path)
from ihav_openrouter_pareto import ParetoError  # noqa: E402
from ihav_openrouter_pareto.build import build  # noqa: E402
from ihav_openrouter_pareto.cli import configure_stdio  # noqa: E402
from ihav_openrouter_pareto.fetch import fetch  # noqa: E402
from ihav_openrouter_pareto.space import TABLE_URL, Space, as_text, read_json, write_json  # noqa: E402

MODALITIES = "text,image,video,speech,decisions"
# Every video model lists 0/0 catalog token prices; charting those zeros would show each one as free, so the video tab
# gets no price basis until a typed video price route is confirmed and added to the config.
PRICE_COMPONENTS = {"video": []}


def enable(space: Space, modalities: list[str]) -> None:
    """Set the tabs in config.json; give a new modality the catalog token prices and the Table defaults, keep any set value."""
    config = read_json(space.config_path)
    config["modalities"] = modalities
    for modality in modalities:
        config.setdefault("price_components", {}).setdefault(modality, PRICE_COMPONENTS.get(modality, ["input", "output"]))
        config.setdefault("default_metric", {}).setdefault(modality, "usage.weekly_tokens")
        config.setdefault("table_urls", {}).setdefault(modality, TABLE_URL.format(modality))
    write_json(space.config_path, config)


def tabs(report: dict) -> dict:
    """What each tab opens on: its default view, valid / total offers, the frontier, and the metrics marked unavailable."""
    out = {}
    for modality in report["modalities"]:
        default = modality["default"]
        view = modality["views"][f"{default['metric']}|{default['basis']}|all"] if default else None
        out[modality["id"]] = {
            "metric": default and default["metric"], "price": default and default["basis"],
            "valid": len(view["valid"]) if view else 0, "total": view["total"] if view else len(modality["offers"]),
            "excluded": view["excluded"] if view else {}, "frontier": [modality["offers"][i]["id"] for i in view["frontier"]] if view else [],
            "unavailable": [m["id"] for m in modality["metrics"] if m["status"] != "ok"],
        }
    return out


def run(args: argparse.Namespace) -> tuple[dict, int]:
    space = Space(args.project)
    space.init()
    enable(space, [m.strip() for m in args.modalities.split(",") if m.strip()])
    if args.offline:
        _, capture_id = fixture_build.make_capture(args.project)
    else:
        capture_id = fetch(space)["capture_id"]
    result = build(space, capture_id)
    summary = {"mode": "offline" if args.offline else "live", "capture_id": capture_id, "validated": result["validated"],
               "problems": result["problems"], "warnings": result["warnings"],
               "endpoints_failed": [e["model"] for e in space.manifest(capture_id)["endpoints"] if e["error"]], "html": result["html"], "csv": result["csv"],
               "json": result["json"], "tabs": tabs(read_json(Path(result["json"]))["report"])}
    return summary, 0 if result["validated"] else 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenRouter Pareto charts as one HTML page, without an LLM or a browser.")
    parser.add_argument("--project", type=Path, default=Path("."), help="folder that holds .ihav_space/ (default: current folder)")
    parser.add_argument("--modalities", default=MODALITIES, help=f"comma-separated tabs, in order (default: {MODALITIES})")
    parser.add_argument("--offline", action="store_true", help="no network: replay the saved 2026-10-07 answers and Table captures")
    try:
        result, code = run(parser.parse_args(argv))
    except ParetoError as exc:
        result, code = {"error": {"code": exc.code, "message": str(exc)}}, exc.exit_code
    print(json.dumps(result, ensure_ascii=False, indent=1, default=as_text))
    return code


if __name__ == "__main__":
    configure_stdio()
    raise SystemExit(main())
