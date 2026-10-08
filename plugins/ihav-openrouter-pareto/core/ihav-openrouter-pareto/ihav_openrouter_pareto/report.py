"""Precomputed views: one per (modality, metric, price component and unit, offer scope); the page only selects and draws."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from . import __version__
from .normalize import AA_KEYS, ARENA_METRIC, LATENCY_METRIC, TABLE_METRICS, select_price
from .pareto import pareto_front
from .space import as_text, iso, utc_now

SCOPES = ("all", "standard", "batch", "free")
UNIT_LABELS = {"per_m_tokens": "USD per 1M tokens", "per_image": "USD per image", "per_megapixel": "USD per megapixel",
               "per_m_chars": "USD per 1M characters", "per_minute": "USD per minute", "per_second": "USD per second"}
METRIC_TEXT = {
    "aa.intelligence_index": ("Artificial Analysis Intelligence Index", "Intelligence vs price"),
    "aa.coding_index": ("Artificial Analysis Coding Index", "Coding vs price"),
    "aa.agentic_index": ("Artificial Analysis Agentic Index", "Agentic vs price"),
    ARENA_METRIC: ("Arena checks passed, %", "Checks passed vs price"),
    "usage.weekly_tokens": ("Weekly tokens (usage, not quality)", "Weekly usage vs price"),
    "perf.throughput_tps": ("Throughput, tokens per second", "Throughput vs price"),
    "perf.latency_s": ("Latency, seconds", "Latency"),
    LATENCY_METRIC: ("Latency p50, seconds (model page, last 30 minutes)", "Latency"),
}
NOT_AXIS = ("perf.latency_s", LATENCY_METRIC)
NOTES = [
    "Prices are OpenRouter list prices, not the cost of a task; units are never converted, so each chart uses one price unit.",
    "Weekly tokens measure usage, not quality.",
    "A Table price label carries no unit in the captured text; it takes the unit of an equal API price, otherwise it stays 'unknown' and is not plotted.",
    "Routers (price -1) and ~...-latest aliases are excluded by exact id; their raw rows stay in the capture.",
    "Checks passed is OpenRouter's public Arena score for image, video and speech models: checks passed over checks run on the "
    "Arena's own prompts. It rates the model, so every offer of that model shows the same score.",
    "Latency is the lowest provider p50 on the model page over the 30 minutes before the capture, for the standard offer: time to "
    "first token for text, generation time for image and video, full response for speech and decisions. It is a column, not an axis, "
    "because lower is better.",
    "Video prices are OpenRouter's per-second list prices from the model page; with several SKUs or resolution tiers the lowest is "
    "shown as a 'from' lower bound.",
]
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
    definition = {"id": metric_id, "label": label, "title": title, "scale": "log" if metric_id == "usage.weekly_tokens" else "linear",
                  "axis": metric_id not in NOT_AXIS, "status": "ok" if available else "unavailable", "reason": None}
    if metric_id in NOT_AXIS:
        definition["reason"] = "lower is better, and the frontier rule maximises the score; shown in the table and hover only"
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
    paid = any(p["status"] == "ok" and p["value"] > 0 for p in offer["prices"])
    display = obs["raw_label"] if obs["source"] == "table" else ("from " if lower_bound else "") + "$" + short(value)
    return {"x": float(value), "v": as_text(value), "d": display, "q": obs["qualifier"], "s": obs["source"], "raw": obs["raw_label"],
            "col": obs["column"], "lb": lower_bound, "fc": value == 0 and paid, "dp": obs["discount_pct"]}


def tab_metrics(offer: dict, modality: str) -> dict:
    """Catalog and Table metrics plus the ones read for this tab only (Arena tab, latency workload)."""
    return {**offer["metrics"], **offer.get("tab_metrics", {}).get(modality, {})}


def offer_entry(offer: dict, bases: list[dict], metrics: list[str], modality: str) -> dict:
    prices = {b["id"]: price_entry(offer, b["component"], b["unit"]) for b in bases}
    found = tab_metrics(offer, modality)
    values = {m: found[m] for m in metrics if m in found}
    ok_prices = [p for p in offer["prices"] if p["status"] == "ok"]
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


def build_view(entries: list[dict], metric: str, basis: str, scope: str, incomplete_tables: bool) -> dict:
    in_scope = [i for i, e in enumerate(entries) if scope == "all" or e["variant"] == scope]
    valid, excluded = [], Counter()
    for i in in_scope:
        reason = exclusion_reason(entries[i], metric, basis, incomplete_tables)
        if reason:
            excluded[reason] += 1
        else:
            valid.append(i)
    price = lambda i: Decimal(entries[i]["p"][basis]["v"])  # noqa: E731
    score = lambda i: Decimal(entries[i]["m"][metric]["v"])  # noqa: E731
    valid.sort(key=lambda i: (price(i), -score(i), entries[i]["id"]))
    notes = [LOWER_BOUND_NOTE] if any(entries[i]["p"][basis]["lb"] for i in valid) else []
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
        bases += [{"id": f"{component}|{u}", "component": component, "unit": u, "label": f"{component.replace('_', ' ')} · {UNIT_LABELS[u]}"} for u in units]
    entries = [offer_entry(o, bases, metric_ids, modality) for o in members]
    views = {f"{m['id']}|{b['id']}|{s}": build_view(entries, m["id"], b["id"], s, incomplete_tables)
             for m in metrics if m["axis"] and m["status"] == "ok" for b in bases for s in SCOPES}
    return {"id": modality, "label": modality.capitalize(), "metrics": metrics, "bases": bases, "scopes": list(SCOPES),
            "offers": entries, "views": views, "default": default_view(metrics, bases, views, config["default_metric"].get(modality))}


def default_view(metrics: list[dict], bases: list[dict], views: dict, preferred: str | None) -> dict | None:
    """The configured metric (else the first chartable one) with the price basis that has the most valid offers."""
    chartable = [m["id"] for m in metrics if m["axis"] and m["status"] == "ok"]
    if not chartable or not bases:
        return None
    metric = preferred if preferred in chartable else chartable[0]
    basis = max(bases, key=lambda b: len(views[f"{metric}|{b['id']}|all"]["valid"]))["id"]
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
