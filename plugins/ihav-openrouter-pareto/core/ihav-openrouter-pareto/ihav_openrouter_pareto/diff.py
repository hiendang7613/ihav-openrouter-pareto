"""`diff`: changes between two captures, comparing only the same metric identity and the same price basis."""

from __future__ import annotations

from .normalize import load_capture
from .space import Space, as_text


def _prices(offer: dict) -> dict:
    return {f"{p['component']}|{p['unit']}|{p['source']}|{p['column']}": p["value"] for p in offer["prices"] if p["status"] == "ok"}


def _metrics(offer: dict) -> dict:
    """Catalog and Table metrics by id; per-tab metrics (Arena, latency) as `<modality>:<id>`."""
    tabs = {f"{tab}:{k}": v["value"] for tab, values in offer.get("tab_metrics", {}).items() for k, v in values.items()}
    return {**{k: v["value"] for k, v in offer["metrics"].items()}, **tabs}


def _compare(kind: str, offer_id: str, a: dict, b: dict, changes: list, refused: list) -> None:
    for key in sorted(set(a) | set(b)):
        if key in a and key in b:
            if a[key] != b[key]:
                changes.append({"offer": offer_id, kind: key, "a": as_text(a[key]), "b": as_text(b[key])})
        else:
            side = "a" if key in a else "b"
            refused.append({"offer": offer_id, kind: key, "reason": f"only in capture {side}; not comparable"})


def diff(space: Space, ref_a: str, ref_b: str) -> dict:
    config = space.config()
    ids = [space.resolve_capture(ref_a), space.resolve_capture(ref_b)]
    sides = [{o["id"]: o for o in load_capture(space.capture_dir(i), config)["offers"]} for i in ids]
    a, b = sides
    price_changes, metric_changes, refused = [], [], []
    for offer_id in sorted(set(a) & set(b)):
        _compare("price_basis", offer_id, _prices(a[offer_id]), _prices(b[offer_id]), price_changes, refused)
        _compare("metric", offer_id, _metrics(a[offer_id]), _metrics(b[offer_id]), metric_changes, refused)
    return {"a": ids[0], "b": ids[1], "offers_added": sorted(set(b) - set(a)), "offers_removed": sorted(set(a) - set(b)),
            "price_changes": price_changes, "metric_changes": metric_changes, "not_comparable": refused}
