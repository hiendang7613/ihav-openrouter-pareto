"""`build`: normalise a capture, write the outputs, check them, and move `latest` only when the build validates."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from pathlib import Path

from .normalize import load_capture
from .render import csv_rows, write_outputs
from .report import build_report
from .space import Space


def check_outputs(folder: Path, report: dict) -> list[str]:
    """The page, CSV and JSON must carry the same observations and frontiers as the report."""
    problems = []
    expected = json.loads(json.dumps(report))
    page = (folder / "pareto.html").read_text(encoding="utf-8")
    match = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', page, re.S)
    if not match or json.loads(match.group(1)) != expected:
        problems.append("pareto.html: embedded data differs from the report")
    if json.loads((folder / "offers.json").read_text(encoding="utf-8"))["report"] != expected:
        problems.append("offers.json: report differs")
    for modality in report["modalities"]:
        with open(folder / f"{modality['id']}.csv", encoding="utf-8", newline="") as handle:
            rows = sum(1 for _ in csv.reader(handle)) - 1
        if rows != sum(1 for _ in csv_rows(report, modality)):
            problems.append(f"{modality['id']}.csv: row count differs from the views")
    return problems


def history_rows(report: dict):
    for modality in report["modalities"]:
        for key, view in modality["views"].items():
            metric, component, unit, scope = key.split("|")
            if scope != "all":
                continue
            for i in view["valid"]:
                offer = modality["offers"][i]
                price = offer["p"][f"{component}|{unit}"]
                yield {"capture_id": report["capture_id"], "captured_at": report["captured_at"], "offer": offer["id"], "metric": metric,
                       "basis": f"{component}|{unit}", "price": price["v"], "price_source": price["s"], "price_qualifier": price["q"],
                       "score": offer["m"][metric]["v"]}


def build(space: Space, capture_ref: str | None = None) -> dict:
    config = space.config()
    capture_id = space.resolve_capture(capture_ref)
    catalog = load_capture(space.capture_dir(capture_id), config)
    report = build_report(catalog, config)
    final = space.builds / capture_id
    temporary = space.builds / f".tmp-{capture_id}"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True)
    try:
        write_outputs(temporary, catalog, report)
        problems = list(catalog["blocking"]) + check_outputs(temporary, report)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    if final.exists():
        shutil.rmtree(final)
    os.replace(temporary, final)
    validated = not problems
    added = 0
    if validated:
        space.publish_latest(capture_id)
        added = space.add_history(history_rows(report))
    return {"capture_id": capture_id, "validated": validated, "problems": problems, "warnings": catalog["warnings"],
            "latest": space.latest(), "history_rows_added": added, "html": str(final / "pareto.html"), "json": str(final / "offers.json"),
            "csv": {m["id"]: str(final / f"{m['id']}.csv") for m in report["modalities"]},
            "views": {m["id"]: {"default": m["default"], "views": len(m["views"]), "offers": len(m["offers"])} for m in report["modalities"]}}
