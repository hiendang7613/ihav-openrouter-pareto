"""Turn one capture into offers keyed by the verbatim API id, with typed price observations and metric values."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import ParetoError
from .space import as_text, sha256_file
from .table import parse_table

# Catalog pricing fields are USD per token; they are shown per 1M tokens (an exact decimal shift).
TOKEN_FIELDS = {
    "prompt": "input", "completion": "output", "image_output": "image_output", "image_token": "image_token",
    "audio": "audio", "audio_output": "audio_output", "internal_reasoning": "internal_reasoning",
    "input_cache_read": "input_cache_read", "input_cache_write": "input_cache_write",
    "input_cache_write_1h": "input_cache_write_1h", "input_audio_cache": "input_audio_cache",
}
ENDPOINT_UNITS = {"image": "per_image", "megapixel": "per_megapixel", "minute": "per_minute", "million_characters": "per_m_chars"}
# Which typed components a Table price column may confirm; one price spanning both columns may confirm either side.
INPUT_COMPONENTS, OUTPUT_COMPONENTS = {"input"}, {"output", "image_output", "audio_output", "output_image"}
TABLE_COLUMN_COMPONENTS = {"Input": INPUT_COMPONENTS, "Output": OUTPUT_COMPONENTS, "Single": INPUT_COMPONENTS | OUTPUT_COMPONENTS}
TABLE_METRICS = {"Weekly Tokens": "usage.weekly_tokens", "Latency": "perf.latency_s", "Throughput": "perf.throughput_tps"}
AA_KEYS = ("intelligence_index", "coding_index", "agentic_index")
SOURCE_ORDER = ("table", "endpoint", "api")
ARENA_METRIC, LATENCY_METRIC = "arena.checks_passed_pct", "stats.latency_p50_s"


def variant(model_id: str) -> str:
    """Offer scope from the id suffix; other suffixes such as :nitro count as standard."""
    suffix = model_id.rsplit(":", 1)[1] if ":" in model_id else ""
    return suffix if suffix in ("batch", "free") else "standard"


def decimal(raw) -> Decimal | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def observation(column, raw, component, unit, source, capture_id, scale=0, qualifier="exact", discount_pct=None, raw_label=None) -> dict:
    """One price as published; -1 is the router sentinel, never a price; 0 is a valid price."""
    value = decimal(raw)
    if value is None:
        status = "invalid"
    elif value == -1:
        status, value = "sentinel", None
    elif value < 0:
        status, value = "invalid", None
    else:
        status, value = "ok", value.scaleb(scale)
    return {"column": column, "raw_label": raw_label or str(raw), "value": value, "currency": "USD", "unit": unit, "component": component,
            "qualifier": qualifier, "discount_pct": discount_pct, "source": source, "capture_id": capture_id, "status": status}


def api_prices(pricing: dict, capture_id: str) -> list[dict]:
    out = []
    for field, raw in sorted(pricing.items()):
        if field == "overrides":  # long-context tiers stay in the raw capture; charts use the base price
            continue
        component = TOKEN_FIELDS.get(field, field)
        unit = "per_m_tokens" if field in TOKEN_FIELDS else "unknown"
        out.append(observation(field, raw, component, unit, "api", capture_id, scale=6 if unit == "per_m_tokens" else 0))
    return out


def endpoint_prices(document: dict, capture_id: str) -> list[dict]:
    out = []
    for endpoint in document.get("endpoints") or []:
        for price in endpoint.get("pricing") or []:
            unit = ENDPOINT_UNITS.get(price.get("unit"), "unknown")
            out.append(observation(f"endpoint:{endpoint.get('provider_slug')}", price.get("cost_usd"), price.get("billable"), unit, "endpoint", capture_id))
    return out


def api_metrics(benchmarks: dict | None) -> dict:
    metrics = {}
    benchmarks = benchmarks or {}
    for key in AA_KEYS:
        value = decimal((benchmarks.get("artificial_analysis") or {}).get(key))
        if value is not None:
            metrics[f"aa.{key}"] = {"value": value, "raw": as_text(value), "source": "api"}
    for entry in benchmarks.get("design_arena") or []:
        value = decimal(entry.get("elo"))
        if value is not None:  # one identity per arena and category; categories are never merged
            metrics[f"da.{entry.get('arena')}/{entry.get('category')}.elo"] = {"value": value, "raw": as_text(value), "source": "api",
                                                                              "rank": entry.get("rank"), "win_rate": entry.get("win_rate")}
    return metrics


def exclusion(row: dict, routers: dict) -> dict | None:
    if row["id"] in routers:
        return {"reason": "router", "detail": routers[row["id"]]}
    if any(decimal(v) == -1 for k, v in (row.get("pricing") or {}).items() if k != "overrides"):
        return {"reason": "router", "detail": "price -1 sentinel; id is not in the router list"}
    if row.get("alias_target"):
        return {"reason": "alias", "detail": f"alias of {row['alias_target'].get('slug')}"}
    return None


def make_offer(row: dict, routers: dict, endpoints: dict | None, capture_id: str) -> dict:
    return {
        "id": row["id"],
        "name": row.get("name") or row["id"],
        "variant": variant(row["id"]),
        "modalities": list(row.get("architecture", {}).get("output_modalities") or []),
        "created": row.get("created"),
        "context_length": row.get("context_length"),
        "canonical_slug": row.get("canonical_slug"),
        "alias_target": (row.get("alias_target") or {}).get("slug"),
        "aliases": [],
        "excluded": exclusion(row, routers),
        "match": "api",
        "table": None,
        "prices": api_prices(row.get("pricing") or {}, capture_id) + (endpoint_prices(endpoints, capture_id) if endpoints else []),
        "metrics": api_metrics(row.get("benchmarks")),
        "tab_metrics": {},  # per modality: values read for one tab only (Arena tab, latency workload)
    }


def table_offer(row: dict, modality: str) -> dict:
    """A Table row with no API match keeps only what the Table showed; no API price is guessed for it."""
    return {"id": row["slug"] or row["name"], "name": row["name"], "variant": variant(row["slug"]), "modalities": [modality],
            "created": None, "context_length": None, "canonical_slug": None, "alias_target": None, "aliases": [],
            "excluded": None, "match": "unmatched", "table": None, "prices": [], "metrics": {}, "tab_metrics": {}}


def arena_metric(standing: dict | None, entry: dict) -> dict | None:
    """Checks passed over checks run in OpenRouter's public Arena, as an exact percentage."""
    passed, total = (standing or {}).get("checksPassed"), (standing or {}).get("checksTotal")
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in (passed, total)) or total <= 0 or not 0 <= passed <= total:
        return None
    value = Decimal(passed) * 100 / Decimal(total)
    runs = f", {standing['scoredRun']} scored runs" if isinstance(standing.get("scoredRun"), int) else ""
    return {"value": value, "raw": f"{passed}/{total}", "display": f"{value.quantize(Decimal('0.1'))}% ({passed}/{total} checks{runs})",
            "source": f"arena:{entry['modality']}", "checks_total": total, "scored_run": standing.get("scoredRun"),
            "evals_run": standing.get("evalsRun"), "captured_at": entry["fetched_at"]}


def latency_metric(endpoints: list, entry: dict) -> dict | None:
    """The lowest provider p50 latency of the model page (milliseconds in the answer), in seconds, with the provider and window."""
    seen = []
    for endpoint in endpoints:
        stats = endpoint.get("stats") or {}
        ms = decimal(stats.get("p50_latency"))
        if ms is not None and ms >= 0:
            seen.append((ms, endpoint.get("provider_name") or endpoint.get("provider_slug"), stats))
    if not seen:
        return None
    ms, provider, stats = min(seen, key=lambda s: s[0])
    value = ms / 1000
    return {"value": value, "raw": f"{as_text(ms)} ms", "display": f"{format(float(value), '.3g')} s p50, {provider}",
            "source": f"stats:{entry['modality']}", "provider": provider, "latency_metric": stats.get("latency_metric"),
            "request_count": stats.get("request_count"), "window_minutes": stats.get("window_minutes"), "captured_at": entry["fetched_at"]}


def video_prices(endpoints: list, capture_id: str) -> list[dict]:
    """Every per-second SKU and tier the model page lists; other units (per megapixel-second, per M tokens) stay in the capture only."""
    out = []
    for endpoint in endpoints:
        for item in endpoint.get("display_pricing") or []:
            if item.get("unitLabel") != "/second" or item.get("displayMultiplier", 1) != 1:
                continue
            sku = item.get("sku_label") or "video"
            labels = [(sku, item.get("price"))] + [(f"{sku} {t.get('sku_label')}", t.get("price")) for t in item.get("tiers") or []]
            for label, price in labels:
                out.append(observation(f"stats:{endpoint.get('provider_slug')}:{label}", price, "video_output", "per_second", "endpoint",
                                       capture_id, raw_label=f"${price}/second, {label}"))
    return out


def attach_page_data(offers: dict, manifest: dict, folder: Path, capture_id: str) -> None:
    """Arena scores go to every offer of the model; latency and video prices (read for variant=standard) to the standard offer only."""
    by_permaslug = {}
    for offer in offers.values():
        by_permaslug.setdefault(offer["canonical_slug"], []).append(offer)
    for source in ("arena", "stats"):
        for entry in manifest.get(source, []):
            if entry["status"] != "ok":
                continue
            data = json.loads((folder / entry["file"]).read_text(encoding="utf-8")).get("data")
            if source == "arena":
                metric = arena_metric((data or {}).get("standing"), entry)
                targets = by_permaslug.get(entry["permaslug"], [])
            else:
                metric = latency_metric(data if isinstance(data, list) else [], entry)
                targets = [o for o in by_permaslug.get(entry["permaslug"], []) if ":" not in o["id"]]
            for offer in targets:
                tab = offer["tab_metrics"].setdefault(entry["modality"], {})
                if metric is not None:
                    tab[ARENA_METRIC if source == "arena" else LATENCY_METRIC] = metric
                if source == "stats" and entry["modality"] == "video":
                    offer["prices"] += video_prices(data if isinstance(data, list) else [], capture_id)


def corroborate(price: dict, structured: list[dict]) -> None:
    """A Table label has no unit in the text; adopt the unit of the one structured price of equal value, else `unknown`."""
    allowed = TABLE_COLUMN_COMPONENTS[price["column"]]
    hits = {(o["component"], o["unit"]) for o in structured
            if o["status"] == "ok" and o["unit"] != "unknown" and o["value"] == price["value"] and o["component"] in allowed}
    if len(hits) == 1:
        price["component"], price["unit"] = hits.pop()
        price["unit_from"] = "equal structured price"
    else:
        price["component"], price["unit"] = price["column"].lower(), "unknown"
        price["unit_from"] = "ambiguous" if hits else "no equal structured price"


def attach_table(offer: dict, row: dict, modality: str, entry: dict, capture_id: str) -> None:
    offer["table"] = {"capture": modality, "captured_at": entry.get("captured_at"), "rank": row["rank"], "name": row["name"], "match": row["match"]}
    for column, (label, value) in row["values"].items():
        offer["metrics"][TABLE_METRICS[column]] = {"value": value, "raw": label, "source": f"table:{modality}", "captured_at": entry.get("captured_at")}
    structured = [p for p in offer["prices"] if p["source"] != "table"]
    for price in row["prices"]:
        # A displayed label already includes any discount; it is recorded, never applied again.
        qualifier = price["qualifier"] if price["qualifier"] == "from" or not row["discount_pct"] else "discounted"
        obs = observation(price["column"], price["value"], None, "unknown", "table", capture_id, qualifier=qualifier,
                          discount_pct=row["discount_pct"], raw_label=price["raw_label"])
        corroborate(obs, structured)
        offer["prices"].append(obs)


def load_capture(folder: Path, config: dict) -> dict:
    """Offers for one capture plus what blocks validation (incomplete or changed Table files)."""
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    capture_id = manifest["capture_id"]
    api_file = folder / manifest.get("api", {}).get("file", "api_all.json")
    if not api_file.is_file():
        raise ParetoError(f"capture {capture_id} has no catalog file", "no_catalog", 2)
    rows = json.loads(api_file.read_text(encoding="utf-8"), parse_float=Decimal)["data"]
    endpoints = {e["model"]: json.loads((folder / e["file"]).read_text(encoding="utf-8"), parse_float=Decimal)
                 for e in manifest.get("endpoints", []) if e.get("file")}
    offers = {}
    for row in rows:
        offers[row["id"]] = make_offer(row, config["routers"], endpoints.get(row["id"]), capture_id)
    for offer in offers.values():
        if offer["alias_target"] in offers:
            offers[offer["alias_target"]]["aliases"].append(offer["id"])
    attach_page_data(offers, manifest, folder, capture_id)
    blocking, warnings, unmatched = [], [], []
    by_name = {}
    for offer in offers.values():
        by_name.setdefault(offer["name"], []).append(offer["id"])
    # One Table row per offer: per-modality captures in config order first, then the unfiltered one.
    for modality in [m for m in config["modalities"] if m in manifest["tables"]] + (["all"] if "all" in manifest["tables"] else []):
        entry = manifest["tables"][modality]
        path = folder / entry["file"]
        if sha256_file(path) != entry["sha256"]:
            blocking.append(f"table_{modality}: file changed after ingest")
        table_rows, errors = parse_table(path.read_text(encoding="utf-8"), entry.get("columns"))
        if not entry["complete"] or errors or len(table_rows) != entry["expected_rows"]:
            blocking.append(f"table_{modality}: {len(table_rows)} of {entry['expected_rows']} expected rows, {len(errors)} parse errors")
        for row in table_rows:
            target = _match(row, offers, by_name)
            if target is None and modality != "all":
                target = offers.setdefault(f"table:{row['slug'] or row['name']}", table_offer(row, modality))
                row["match"] = "unmatched"
            if target is None:
                unmatched.append({"table": modality, "slug": row["slug"], "name": row["name"]})
            elif target["table"] is None:
                attach_table(target, row, modality, entry, capture_id)
    for source in ("arena", "stats"):
        entries = manifest.get(source, [])
        skipped = sum(e["status"] == "skipped" for e in entries)
        if skipped:
            cause = next((e["error"] for e in entries if e["status"] == "error" and e.get("http_status") in (401, 403, 429)), "a stop status")
            warnings.append(f"{source} route stopped ({cause}); {skipped} models were not requested and have no {source} data")
    for offer in offers.values():
        if offer["excluded"] and offer["excluded"]["detail"].startswith("price -1 sentinel"):
            warnings.append(f"{offer['id']} has price -1 but is not in the router list; excluded as a router")
    return {"manifest": manifest, "capture_id": capture_id, "offers": list(offers.values()), "unmatched_table_rows": unmatched,
            "blocking": blocking, "warnings": warnings, "incomplete_tables": any(not e["complete"] for e in manifest["tables"].values())}


def _match(row: dict, offers: dict, by_name: dict) -> dict | None:
    """Exact id from the row link first; else the full display name (provider, model and variant) when it is unique."""
    if row["slug"] in offers:
        row["match"] = "id"
        return offers[row["slug"]]
    ids = by_name.get(row["name"], [])
    if len(ids) == 1:
        row["match"] = "name"
        return offers[ids[0]]
    return None


def select_price(offer: dict, component: str, unit: str) -> tuple[dict, bool] | None:
    """One observation per offer for a chart: the first source in SOURCE_ORDER; several values there give the lowest as a lower bound."""
    candidates = [p for p in offer["prices"] if p["status"] == "ok" and p["component"] == component and p["unit"] == unit]
    for source in SOURCE_ORDER:
        group = [p for p in candidates if p["source"] == source]
        if group:
            low = min(group, key=lambda p: p["value"])
            lower_bound = len({p["value"] for p in group}) > 1 or any(p["qualifier"] == "from" for p in group if p["value"] == low["value"])
            return low, lower_bound
    return None
