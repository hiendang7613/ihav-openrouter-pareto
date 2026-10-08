"""Plan 12.3 and bản 4: the frontier equals the pairwise dominance rule (max score, or min latency); views never mix units or Design Arena categories."""

from __future__ import annotations

import itertools
from decimal import Decimal

from ihav_openrouter_pareto.pareto import pareto_front
from ihav_openrouter_pareto.report import LOWER_BOUND_NOTE, short

D = Decimal


def dominates(a, b):
    return a[0] <= b[0] and a[1] >= b[1] and (a[0] < b[0] or a[1] > b[1])


def dominates_lower(a, b):
    """Lower is better (latency): A dominates B when it is no dearer and no slower, and strictly one of them."""
    return a[0] <= b[0] and a[1] <= b[1] and (a[0] < b[0] or a[1] < b[1])


def oracle(points, better="higher"):
    rule = dominates if better == "higher" else dominates_lower
    return {p[2] for p in points if not any(rule(q, p) for q in points if q is not p)}


def test_every_subset_of_a_3x3_grid_matches_pairwise_dominance():
    grid = [(D(c), D(s), f"{c}{s}") for c in range(3) for s in range(3)]
    for size in range(len(grid) + 1):
        for subset in itertools.combinations(grid, size):
            assert set(pareto_front(subset)) == oracle(subset), subset


def test_lower_is_better_frontier_matches_pairwise_dominance_on_every_subset():
    grid = [(D(c), D(s), f"{c}{s}") for c in range(3) for s in range(3)]
    for size in range(len(grid) + 1):
        for subset in itertools.combinations(grid, size):
            assert set(pareto_front((c, -s, k) for c, s, k in subset)) == oracle(subset, "lower"), subset


def test_every_order_of_a_tie_fixture_gives_the_same_frontier():
    # equal price, equal score, co-located offers, a free offer, and a cheaper equal score
    ties = [(D(0), D(1), "free"), (D(2), D(5), "a"), (D(2), D(5), "a-twin"), (D(2), D(4), "a-low"), (D(3), D(5), "b-same-score"),
            (D(1), D(5), "c-cheaper"), (D(4), D(7), "d")]
    expected = {"free", "c-cheaper", "d"}
    for order in itertools.permutations(ties):
        assert set(pareto_front(order)) == expected == oracle(order)


def test_co_located_survivors_are_all_kept_cheapest_first():
    points = [(D(5), D(9), "z"), (D(1), D(3), "x"), (D(1), D(3), "y"), (D(1), D(2), "w")]
    assert pareto_front(points) == ["x", "y", "z"]


def test_exact_decimals_decide_even_when_the_display_rounds_equal():
    cheap, dear = D("9.5808"), D("9.580838")
    assert short(cheap) == short(dear) == "9.581"
    assert pareto_front([(dear, D(10), "dear"), (cheap, D(10), "cheap")]) == ["cheap"]


def test_every_image_and_speech_view_and_the_text_defaults_match_the_pairwise_rule(report):
    checked = 0
    for modality in report["report"]["modalities"]:
        for key, view in modality["views"].items():
            if modality["id"] == "text" and not key.endswith("|all"):
                continue
            metric, component, unit, _ = key.split("|")
            better = next(m["better"] for m in modality["metrics"] if m["id"] == metric)
            points = [(D(modality["offers"][i]["p"][f"{component}|{unit}"]["v"]), D(modality["offers"][i]["m"][metric]["v"]), i) for i in view["valid"]]
            assert set(view["frontier"]) == oracle(points, better), key
            checked += 1
    assert checked > 150


def test_views_use_one_unit_and_missing_scores_are_not_plotted(report):
    image = next(m for m in report["report"]["modalities"] if m["id"] == "image")
    per_image = image["views"]["usage.weekly_tokens|output_image|per_image|all"]
    assert [image["offers"][i]["id"] for i in per_image["valid"]] == ["bytedance-seed/seedream-4.5"]
    assert per_image["notes"] == [LOWER_BOUND_NOTE]
    for modality in report["report"]["modalities"]:
        for key, view in modality["views"].items():
            metric, component, unit, _ = key.split("|")
            assert all(f"{component}|{unit}" in modality["offers"][i]["p"] and metric in modality["offers"][i]["m"] for i in view["valid"])
            assert len(view["valid"]) + sum(view["excluded"].values()) == view["total"]
    text = next(m for m in report["report"]["modalities"] if m["id"] == "text")
    intelligence = text["views"]["aa.intelligence_index|input|per_m_tokens|all"]
    assert len(intelligence["valid"]) == 290 and intelligence["excluded"]["missing_metric"] == 150


def test_design_arena_views_keep_each_category(report):
    text = next(m for m in report["report"]["modalities"] if m["id"] == "text")
    offers = {o["id"]: o for o in text["offers"]}
    assert offers["anthropic/claude-opus-5.5"]["m"]["da.agents/mobileapps.elo"]["v"] == "1328"
    assert offers["anthropic/claude-opus-5"]["m"]["da.agents/mobileapps.elo"]["v"] == "1348"
    assert not any(m["id"].startswith("da.") and m["id"].count("/") != 1 for m in text["metrics"])


def test_free_offers_and_free_components_take_part(report):
    speech = next(m for m in report["report"]["modalities"] if m["id"] == "speech")
    offers = speech["offers"]
    view = speech["views"]["usage.weekly_tokens|input|per_m_tokens|all"]
    assert [offers[i]["id"] for i in view["frontier"]] == ["fish-audio/s2.1-pro-free:free", "google/gemini-3.8-flash-tts"]
    free = next(o for o in offers if o["id"] == "fish-audio/s2.1-pro-free:free")
    kokoro = next(o for o in offers if o["id"] == "hexgrad/kokoro-82m")
    assert free["free"] and free["p"]["input|per_m_tokens"]["x"] == 0
    assert kokoro["p"]["output|per_m_tokens"]["fc"] and not kokoro["free"]


def test_scope_filters_recompute_the_frontier(report):
    text = next(m for m in report["report"]["modalities"] if m["id"] == "text")
    views = {s: text["views"][f"aa.intelligence_index|input|per_m_tokens|{s}"] for s in text["scopes"]}
    variants = {s: {text["offers"][i]["variant"] for i in views[s]["valid"]} for s in ("standard", "batch", "free")}
    assert variants == {"standard": {"standard"}, "batch": {"batch"}, "free": {"free"}}
    assert any(text["offers"][i]["variant"] == "batch" for i in views["all"]["frontier"])
    assert all(text["offers"][i]["variant"] == "standard" for i in views["standard"]["frontier"])
