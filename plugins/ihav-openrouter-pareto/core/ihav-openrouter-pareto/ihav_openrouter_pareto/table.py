"""The `|`-separated Table text the skill reads from openrouter.ai/models, and `ingest` into a capture."""

from __future__ import annotations

import re
import shutil
import urllib.parse
from decimal import Decimal
from pathlib import Path

from . import ParetoError
from .space import Space, iso, sha256_file, utc_now

MISSING = "—"
SPAN = re.compile(r"^(.*)\{(\d+)\}$")
PRICE = re.compile(r"^(from )?\$(\d[\d,]*(?:\.\d+)?)$")
DISCOUNT = re.compile(r"\s(\d+(?:\.\d+)?)% off$")
SCALE = {"": 0, "K": 3, "M": 6, "B": 9, "T": 12}
NUMBER_COLUMNS = ("Weekly Tokens", "Latency", "Throughput")


def weekly_tokens(label: str) -> Decimal:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMBT]?)", label)
    if not match:
        raise ValueError(f"weekly tokens {label!r}")
    return Decimal(match.group(1)).scaleb(SCALE[match.group(2)])


def latency_seconds(label: str) -> Decimal:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)ms", label)
    if match:
        return Decimal(match.group(1)) / 1000
    match = re.fullmatch(r"(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?", label)
    if not match or not any(match.groups()):
        raise ValueError(f"latency {label!r}")
    return Decimal(match.group(1) or 0) * 60 + Decimal(match.group(2) or 0)


def throughput(label: str) -> Decimal:
    match = re.fullmatch(r"(\d+(?:\.\d+)?) t/s", label)
    if not match:
        raise ValueError(f"throughput {label!r}")
    return Decimal(match.group(1))


PARSERS = {"Weekly Tokens": weekly_tokens, "Latency": latency_seconds, "Throughput": throughput}


def price_label(label: str) -> tuple[Decimal, str]:
    match = PRICE.fullmatch(label)
    if not match:
        raise ValueError(f"price {label!r}")
    return Decimal(match.group(2).replace(",", "")), "from" if match.group(1) else "exact"


def header_columns(text: str) -> list[str] | None:
    for line in text.splitlines():
        if line.startswith("# Columns:"):
            return [c.strip() for c in line[len("# Columns:"):].split("|")]
    return None


def parse_table(text: str, columns: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Return (rows, errors). A cell `value{n}` spans n columns, so later cells shift left (plan fixture notes)."""
    columns = header_columns(text) or columns
    if not columns or "slug" not in columns:
        raise ParetoError("Table text needs a '# Columns:' line (or --columns) that names a slug column", "bad_table", 2)
    rows, errors = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cells, spans = [], {}
        for raw in line.split("|"):
            match = SPAN.match(raw)
            width = int(match.group(2)) if match else 1
            if width > 1:
                spans[len(cells)] = width
            cells.extend([match.group(1) if match else raw] + [None] * (width - 1))
        if len(cells) != len(columns):
            errors.append(f"line {number}: {len(cells)} cells, expected {len(columns)}")
            continue
        row, problems = _row(dict(zip(columns, cells)), {columns[i]: columns[i:i + w] for i, w in spans.items()}, len(rows) + 1)
        errors.extend(f"line {number}: {p}" for p in problems)
        rows.append(row)
    return rows, errors


def _row(cells: dict, spans: dict, position: int) -> tuple[dict, list[str]]:
    name = (cells.get("Model Name") or "").strip()
    discount = DISCOUNT.search(name)
    row = {
        "slug": cells["slug"].strip(),
        "name": DISCOUNT.sub("", name),
        "rank": int(cells["index"]) + 1 if (cells.get("index") or "").isdigit() else position,
        "discount_pct": discount.group(1) if discount else None,
        "values": {},
        "prices": [],
    }
    problems = []
    for column in NUMBER_COLUMNS:
        label = (cells.get(column) or "").strip()
        if column in cells and label and label != MISSING:
            try:
                row["values"][column] = (label, PARSERS[column](label))
            except ValueError as exc:
                problems.append(str(exc))
    joined = spans.get("Input", [])[:2] == ["Input", "Output"]
    for column in (("Input",) if joined else ("Input", "Output")):
        label = (cells.get(column) or "").strip()
        if column not in cells or not label or label == MISSING:
            continue
        try:
            value, qualifier = price_label(label)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        row["prices"].append({"column": "Single" if joined else column, "raw_label": label, "value": value, "qualifier": qualifier})
    return row, problems


def ingest(space: Space, capture_id: str, modality: str, file: Path, url: str, expected_rows: int, view: str = "table",
           captured_at: str | None = None, columns: list[str] | None = None) -> dict:
    """Store the pasted Table text in the capture and record whether every expected row arrived."""
    config = space.config()
    if view != "table":
        raise ParetoError("only --view table is supported", "bad_view", 2)
    if modality not in config["modalities"] and modality != "all":
        raise ParetoError(f"modality {modality!r} is not in config.json", "bad_modality", 2)
    capture_id = space.resolve_capture(capture_id)
    text = Path(file).read_text(encoding="utf-8")
    rows, errors = parse_table(text, columns)
    target = space.capture_dir(capture_id) / f"table_{modality}.txt"
    if Path(file).resolve() != target.resolve():
        shutil.copyfile(file, target)
    entry = {
        "file": target.name,
        "url": url,
        "filters": dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)),
        "view": view,
        "captured_at": captured_at or iso(utc_now()),
        "columns": header_columns(text) or columns,
        "expected_rows": expected_rows,
        "rows_read": len(rows),
        "complete": expected_rows == len(rows) and not errors,
        "errors": errors[:50],
        "sha256": sha256_file(target),
    }
    manifest = space.manifest(capture_id)
    manifest["tables"][modality] = entry
    space.save_manifest(capture_id, manifest)
    return {"capture_id": capture_id, "modality": modality, **entry}
