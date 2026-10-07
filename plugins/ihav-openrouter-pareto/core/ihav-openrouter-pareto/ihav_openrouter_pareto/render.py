"""HTML, CSV and JSON outputs, all written from the same report (one set of observations and frontiers)."""

from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

from .space import as_text

ASSETS = Path(__file__).with_name("assets")
CSV_COLUMNS = ["capture_id", "modality", "metric", "metric_label", "price_component", "price_unit", "offer_id", "offer_name", "variant",
               "price", "price_display", "price_raw_label", "price_column", "price_qualifier", "discount_pct", "price_source",
               "lower_bound", "free_offer", "free_component", "score", "score_display"] + [f"frontier_{s}" for s in ("all", "standard", "batch", "free")]
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?")


def embed_json(data) -> str:
    """JSON for a <script type="application/json"> block; `<` cannot end the block once escaped."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")


def render_html(report: dict) -> str:
    parts = {
        "TITLE": html.escape(f"OpenRouter Pareto {report['capture_id']}"),
        "STYLE": (ASSETS / "style.css").read_text(encoding="utf-8"),
        "SCRIPT": (ASSETS / "app.js").read_text(encoding="utf-8"),
        "DATA": embed_json(report),
    }
    page = (ASSETS / "page.html").read_text(encoding="utf-8")
    return re.sub(r"__(TITLE|STYLE|SCRIPT|DATA)__", lambda m: parts[m.group(1)], page)


def csv_safe(value) -> str:
    """Spreadsheet formula guard: a text cell that starts like a formula gets a leading apostrophe; numbers stay as they are."""
    text = "" if value is None else str(value)
    if text.startswith(FORMULA_START) and not NUMBER.fullmatch(text):
        return "'" + text
    return text


def csv_rows(report: dict, modality: dict):
    """One row per valid offer in each (metric, price basis) view, with frontier membership for every scope."""
    for metric in modality["metrics"]:
        for basis in modality["bases"]:
            key = f"{metric['id']}|{basis['id']}"
            if f"{key}|all" not in modality["views"]:
                continue
            fronts = {s: set(modality["views"][f"{key}|{s}"]["frontier"]) for s in modality["scopes"]}
            for i in modality["views"][f"{key}|all"]["valid"]:
                offer = modality["offers"][i]
                price, score = offer["p"][basis["id"]], offer["m"][metric["id"]]
                flags = ["yes" if i in fronts[s] else ("no" if s in ("all", offer["variant"]) else "") for s in ("all", "standard", "batch", "free")]
                yield [report["capture_id"], modality["id"], metric["id"], metric["label"], basis["component"], basis["unit"], offer["id"], offer["name"],
                       offer["variant"], price["v"], price["d"], price["raw"], price["col"], price["q"], price["dp"], price["s"],
                       price["lb"], offer["free"], price["fc"], score["v"], score["d"]] + flags


def write_csv(path: Path, report: dict, modality: dict) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for row in csv_rows(report, modality):
            writer.writerow([csv_safe(v) for v in row])
            count += 1
    return count


def write_outputs(folder: Path, catalog: dict, report: dict) -> None:
    offers_json = {"capture_id": catalog["capture_id"], "manifest": catalog["manifest"], "offers": catalog["offers"],
                   "unmatched_table_rows": catalog["unmatched_table_rows"], "report": report}
    (folder / "offers.json").write_text(json.dumps(offers_json, ensure_ascii=False, indent=1, default=as_text) + "\n", encoding="utf-8")
    for modality in report["modalities"]:
        write_csv(folder / f"{modality['id']}.csv", report, modality)
    (folder / "pareto.html").write_text(render_html(report), encoding="utf-8")
