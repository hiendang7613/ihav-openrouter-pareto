"""Precomputed views: one per (modality, metric, price component and unit, offer scope); the page only selects and draws."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from . import __version__
from .normalize import AA_KEYS, ARENA_COST_UNIT, ARENA_METRIC, LATENCY_METRIC, LIST_SOURCES, TABLE_METRICS, select_price
from .pareto import pareto_front
from .space import as_text, iso, utc_now

SCOPES = ("all", "standard", "batch", "free")
UNIT_LABELS = {"per_m_tokens": "USD per 1M tokens", "per_image": "USD per image", "per_megapixel": "USD per megapixel",
               "per_m_chars": "USD per 1M characters", "per_minute": "USD per minute", "per_second": "USD per second",
               ARENA_COST_UNIT: "USD per Arena task (measured mean, not a list price)"}
METRIC_TEXT = {
    "aa.intelligence_index": ("Artificial Analysis Intelligence Index", "Intelligence vs price"),
    "aa.coding_index": ("Artificial Analysis Coding Index", "Coding vs price"),
    "aa.agentic_index": ("Artificial Analysis Agentic Index", "Agentic vs price"),
    ARENA_METRIC: ("Arena checks passed, %", "Checks passed vs price"),
    "usage.weekly_tokens": ("Weekly tokens (usage, not quality)", "Weekly usage vs price"),
    "perf.throughput_tps": ("Throughput, tokens per second", "Throughput vs price"),
    "perf.latency_s": ("Latency, seconds (Table)", "Latency vs price (speed, not quality; lower is better)"),
    LATENCY_METRIC: ("Latency p50, seconds (model page, last 30 minutes)", "Latency vs price (speed, not quality; lower is better)"),
}
# Lower is better for these; their frontier is minimum price and minimum value (plan bản 4).
LOWER_BETTER = ("perf.latency_s", LATENCY_METRIC)
LOG_SCALE = ("usage.weekly_tokens", "perf.latency_s", LATENCY_METRIC)
NOTES = [
    "Prices are OpenRouter list prices, not the cost of a task, except the basis 'USD per Arena task (measured)'; units are never "
    "converted, so each chart uses one price unit.",
    "Weekly tokens measure usage, not quality.",
    "A Table price label carries no unit in the captured text; it takes the unit of an equal API price, otherwise it stays 'unknown' and is not plotted.",
    "Routers (price -1) and ~...-latest aliases are excluded by exact id; their raw rows stay in the capture.",
    "Checks passed is OpenRouter's public Arena score for image, video and speech models: checks passed over checks run on the "
    "Arena's own prompts. It rates the model, so every offer of that model shows the same score.",
    "Latency is the lowest provider p50 on the model page over the 30 minutes before the capture, for the standard offer: time to "
    "first token for text, generation time for image and video, full response for speech and decisions. A latency chart shows "
    "speed, not quality; lower is better.",
    "Video prices are OpenRouter's per-second list prices from the model page, without video-input SKUs; with several SKUs or "
    "resolution tiers the lowest is shown as a 'from' lower bound.",
    "'USD per Arena task (measured)' is the mean cost OpenRouter's Arena recorded for the model's own scored tasks (n in hover). "
    "It is a measured cost, not a list price; each model's task set can differ slightly, and a video task is one clip at the "
    "Arena's own length and resolution.",
]
LOWER_BETTER_NOTE = "Lower is better: the step line is the lowest value observed at a price up to that point."
MEASURED_NOTE = "Prices on this chart are measured Arena costs per task, not list prices."
LOWER_BOUND_NOTE = "Prices marked 'from' are lower bounds; the frontier uses the displayed price at display precision."


def short(value: Decimal) -> str:
    """Four significant digits for display only; every comparison uses the exact Decimal."""
    if value == 0:
        return "0"
    rounded = value.quantize(Decimal(1).scaleb(value.adjusted() - 3)).normalize()
    return format(rounded, "f")


def metric_def(metric_id: str, available: bool) -> dict:
    if metric_id.startswith("da."):
        name = metric_id[3:-4]
        label, title = f"Design Arena ELO, {name}", f"Design Arena {name} ELO vs price"
    else:
        label, title = METRIC_TEXT.get(metric_id, (metric_id, f"{metric_id} vs price"))
    definition = {"id": metric_id, "label": label, "title": title, "scale": "log" if metric_id in LOG_SCALE else "linear",
                  "better": "lower" if metric_id in LOWER_BETTER else "higher", "status": "ok" if available else "unavailable", "reason": None}
    if not available:
        definition["reason"] = "no Table capture for this modality (browser step not run); API-only build"
    return definition


def metric_order(metric_id: str) -> tuple:
    fixed = [f"aa.{k}" for k in AA_KEYS] + [ARENA_METRIC, "usage.weekly_tokens", "perf.throughput_tps", "perf.latency_s", LATENCY_METRIC]
    return (fixed.index(metric_id), "") if metric_id in fixed else (len(fixed), metric_id)


def price_entry(offer: dict, component: str, unit: str) -> dict | None:
    chosen = select_price(offer, component, unit)
    if chosen is None:
        return None
    obs, lower_bound = chosen
    value = obs["value"]
    paid = any(p["value"] > 0 for p in list_prices(offer))
    display = obs["raw_label"] if obs["source"] == "table" else ("from " if lower_bound else "") + "$" + short(value)
    return {"x": float(value), "v": as_text(value), "d": display, "q": obs["qualifier"], "s": obs["source"], "raw": obs["raw_label"],
            "col": obs["column"], "lb": lower_bound, "fc": value == 0 and paid, "dp": obs["discount_pct"], "n": obs.get("sample_n")}


def list_prices(offer: dict) -> list[dict]:
    """Valid list prices; a measured Arena cost never makes an offer paid or free."""
    return [p for p in offer["prices"] if p["status"] == "ok" and p["source"] in LIST_SOURCES]


def tab_metrics(offer: dict, modality: str) -> dict:
    """Catalog and Table metrics plus the ones read for this tab only (Arena tab, latency workload)."""
    return {**offer["metrics"], **offer.get("tab_metrics", {}).get(modality, {})}


def offer_entry(offer: dict, bases: list[dict], metrics: list[str], modality: str) -> dict:
    prices = {b["id"]: price_entry(offer, b["component"], b["unit"]) for b in bases}
    found = tab_metrics(offer, modality)
    values = {m: found[m] for m in metrics if m in found}
    ok_prices = list_prices(offer)
    return {
        "id": offer["id"], "name": offer["name"], "variant": offer["variant"], "match": offer["match"],
        "excluded": (offer["excluded"] or {}).get("reason"), "detail": (offer["excluded"] or {}).get("detail"),
        "alias_target": offer["alias_target"], "aliases": offer["aliases"], "rank": (offer["table"] or {}).get("rank"),
        "free": bool(ok_prices) and all(p["value"] == 0 for p in ok_prices),
        "p": {k: v for k, v in prices.items() if v is not None},
        "m": {k: {"y": float(v["value"]), "v": as_text(v["value"]),
                  "d": v.get("display") or (v["raw"] if v["source"].startswith("table") else as_text(v["value"]))} for k, v in values.items()},
    }


def exclusion_reason(entry: dict, metric: str, basis: str, incomplete_tables: bool) -> str | None:
    if entry["excluded"]:
        return entry["excluded"]
    if basis not in entry["p"]:
        return "missing_price"
    if metric not in entry["m"]:
        return "capture_incomplete" if incomplete_tables and metric in TABLE_METRICS.values() else "missing_metric"
    return None


def build_view(entries: list[dict], metric: dict, basis: dict, scope: str, incomplete_tables: bool) -> dict:
    """Valid offers cheapest first, and the frontier: minimum price with maximum score, or minimum value when lower is better."""
    sign = -1 if metric["better"] == "lower" else 1
    metric, measured, basis = metric["id"], basis["measured"], basis["id"]
    in_scope = [i for i, e in enumerate(entries) if scope == "all" or e["variant"] == scope]
    valid, excluded = [], Counter()
    for i in in_scope:
        reason = exclusion_reason(entries[i], metric, basis, incomplete_tables)
        if reason:
            excluded[reason] += 1
        else:
            valid.append(i)
    price = lambda i: Decimal(entries[i]["p"][basis]["v"])  # noqa: E731
    score = lambda i: sign * Decimal(entries[i]["m"][metric]["v"])  # noqa: E731
    valid.sort(key=lambda i: (price(i), -score(i), entries[i]["id"]))
    notes = [LOWER_BOUND_NOTE] if any(entries[i]["p"][basis]["lb"] for i in valid) else []
    notes += ([LOWER_BETTER_NOTE] if sign < 0 else []) + ([MEASURED_NOTE] if measured else [])
    return {"valid": valid, "frontier": pareto_front((price(i), score(i), i) for i in valid), "total": len(in_scope),
            "excluded": dict(sorted(excluded.items())), "notes": notes}


def modality_report(modality: str, offers: list[dict], config: dict, has_table: bool, incomplete_tables: bool) -> dict:
    members = sorted((o for o in offers if modality in o["modalities"]), key=lambda o: o["id"])
    usable = [o for o in members if not o["excluded"]]
    metric_ids = sorted({m for o in usable for m in tab_metrics(o, modality)} | set(TABLE_METRICS.values()), key=metric_order)
    metrics = [metric_def(m, has_table or m not in TABLE_METRICS.values()) for m in metric_ids]
    bases = []
    for component in config["price_components"].get(modality, []):
        units = sorted({p["unit"] for o in usable for p in o["prices"] if p["status"] == "ok" and p["component"] == component and p["unit"] in UNIT_LABELS})
        bases += [{"id": f"{component}|{u}", "component": component, "unit": u, "label": f"{component.replace('_', ' ')} · {UNIT_LABELS[u]}",
                   "measured": u == ARENA_COST_UNIT} for u in units]
    entries = [offer_entry(o, bases, metric_ids, modality) for o in members]
    views = {f"{m['id']}|{b['id']}|{s}": build_view(entries, m, b, s, incomplete_tables)
             for m in metrics if m["status"] == "ok" for b in bases for s in SCOPES}
    return {"id": modality, "label": modality.capitalize(), "metrics": metrics, "bases": bases, "scopes": list(SCOPES),
            "offers": entries, "views": views, "default": default_view(metrics, bases, views, config["default_metric"].get(modality))}


def default_view(metrics: list[dict], bases: list[dict], views: dict, preferred: str | None) -> dict | None:
    """The configured metric (else the first chartable one) with the list-price basis that has the most valid offers;
    the measured Arena cost is never a default (plan bản 4)."""
    chartable = [m["id"] for m in metrics if m["status"] == "ok"]
    listed = [b for b in bases if not b["measured"]]
    if not chartable or not listed:
        return None
    metric = preferred if preferred in chartable else chartable[0]
    basis = max(listed, key=lambda b: len(views[f"{metric}|{b['id']}|all"]["valid"]))["id"]
    return {"metric": metric, "basis": basis, "scope": "all"}


def build_report(catalog: dict, config: dict) -> dict:
    manifest = catalog["manifest"]
    tables = manifest["tables"]
    modalities = [modality_report(m, catalog["offers"], config, m in tables or "all" in tables, catalog["incomplete_tables"])
                  for m in config["modalities"]]
    failed = [e["model"] for e in manifest.get("endpoints", []) if e.get("error")]
    page = {s: dict(Counter(e["status"] for e in manifest.get(s, []))) for s in ("arena", "stats")}
    return {
        "capture_id": catalog["capture_id"], "captured_at": manifest["created_at"], "generated_at": iso(utc_now()), "version": __version__,
        "api_url": manifest["api"]["url"],
        "tables": {m: {k: e[k] for k in ("url", "captured_at", "expected_rows", "rows_read", "complete")} for m, e in tables.items()},
        "endpoints": {"ok": len(manifest.get("endpoints", [])) - len(failed), "failed": len(failed)}, "arena": page["arena"], "stats": page["stats"],
        "warnings": catalog["warnings"], "blocking": catalog["blocking"], "notes": NOTES, "modalities": modalities,
    }
