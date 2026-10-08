"""Plan bản 3: model-page data (Arena "Checks passed", p50 latency per workload, video prices per second), offline."""

from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal

import pytest

from fixture_build import PAGE_FIXTURES, fixture_get, make_capture
from ihav_openrouter_pareto import ParetoError
from ihav_openrouter_pareto.build import build
from ihav_openrouter_pareto.fetch import fetch
from ihav_openrouter_pareto.normalize import ARENA_METRIC, LATENCY_METRIC, load_capture, select_price
from ihav_openrouter_pareto.space import DEFAULT_CONFIG, Space

GEMINI_IMAGE = "google/gemini-3.1-flash-image-preview"


@pytest.fixture(scope="module")
def offers(built):
    space, capture_id, _ = built
    return {o["id"]: o for o in load_capture(space.capture_dir(capture_id), space.config())["offers"]}


@pytest.fixture(scope="module")
def five(tmp_path_factory):
    """The fixtures built with all five tabs, as scripts/charts.py enables them."""
    project = tmp_path_factory.mktemp("five")
    space = Space(project)
    space.init()
    config = json.loads(space.config_path.read_text(encoding="utf-8"))
    config["modalities"] = ["text", "image", "video", "speech", "decisions"]
    space.config_path.write_text(json.dumps(config), encoding="utf-8")
    _, capture_id = make_capture(project)
    result = build(space, capture_id)
    report = json.loads((space.builds / capture_id / "offers.json").read_text(encoding="utf-8"))["report"]
    return space, capture_id, result, {m["id"]: m for m in report["modalities"]}


def entry(modality, offer_id):
    return next(o for o in modality["offers"] if o["id"] == offer_id)


def test_every_page_fixture_matches_its_recorded_sha256():
    listed = [line.split() for line in (PAGE_FIXTURES / "SHA256SUMS").read_text().splitlines() if line.strip()]
    assert len(listed) == 27
    for digest, name in listed:
        assert hashlib.sha256((PAGE_FIXTURES / name).read_bytes()).hexdigest() == digest, name


def test_checks_passed_is_an_exact_share_and_zero_checks_or_404_is_no_score(built, offers):
    space, capture_id, _ = built
    arena = offers[GEMINI_IMAGE]["tab_metrics"]["image"][ARENA_METRIC]
    assert arena["value"] == Decimal(58) * 100 / Decimal(66) and arena["display"] == "87.9% (58/66 checks, 14 scored runs)"
    assert arena["source"] == "arena:image" and arena["checks_total"] == 66
    assert ARENA_METRIC not in offers["openai/gpt-image-2.5-sunburst"]["tab_metrics"].get("image", {})  # 0 of 0 checks
    manifest = {e["permaslug"]: e for e in space.manifest(capture_id)["arena"]}
    assert manifest["inclusionai/ming-image-0.1-design-20260922"]["status"] == "absent"
    assert manifest["inclusionai/ming-image-0.1-design-20260922"]["http_status"] == 404


def test_latency_uses_the_page_workload_of_each_tab(built, report):
    space, capture_id, _ = built
    for e in space.manifest(capture_id)["stats"]:
        perf = DEFAULT_CONFIG["perf_workloads"][e["modality"]]
        assert f"&perfWorkload={perf['workload']}&latencyMetric={perf['latency_metric']}" in e["url"]
    tabs = {m["id"]: m for m in report["report"]["modalities"]}
    text, image = entry(tabs["text"], GEMINI_IMAGE)["m"], entry(tabs["image"], GEMINI_IMAGE)["m"]
    assert text[LATENCY_METRIC]["v"] != image[LATENCY_METRIC]["v"]
    assert ARENA_METRIC in image and ARENA_METRIC not in text
    latency = next(m for m in tabs["text"]["metrics"] if m["id"] == LATENCY_METRIC)
    assert latency["axis"] is False and not any(k.startswith(LATENCY_METRIC) for k in tabs["text"]["views"])


def test_latency_is_the_lowest_provider_p50_and_only_for_the_standard_offer(offers):
    sonnet = offers["anthropic/claude-sonnet-5.5"]["tab_metrics"]["text"][LATENCY_METRIC]
    assert (sonnet["value"], sonnet["provider"], sonnet["latency_metric"]) == (Decimal("0.994"), "Amazon Bedrock", "latency")
    assert LATENCY_METRIC not in offers["anthropic/claude-sonnet-5.5:batch"]["tab_metrics"].get("text", {})


def test_video_prices_are_per_second_from_the_lowest_sku_or_tier(five):
    space, capture_id, _, _ = five
    offers = {o["id"]: o for o in load_capture(space.capture_dir(capture_id), space.config())["offers"]}
    assert [(o["value"], b) for o, b in [select_price(offers["google/veo-3.1"], "video_output", "per_second")]] == [(Decimal("0.20"), True)]
    low, lower_bound = select_price(offers["bytedance/seedance-2.0"], "video_output", "per_second")
    assert (low["value"], lower_bound, low["raw_label"]) == (Decimal("0.0413144"), True, "$0.0413144/second, Video (with video input) 480p")
    assert {p["unit"] for p in offers["bytedance/seedance-2.0"]["prices"] if p["source"] == "endpoint"} == {"per_second"}
    assert select_price(offers["black-forest-labs/flux-video-upscale"], "video_output", "per_second") is None  # per megapixel-second
    assert select_price(offers["heygen/avatar-iv"], "video_output", "per_second")[1] is False


def test_five_tabs_chart_checks_passed_and_carry_latency_in_csv(five):
    space, capture_id, result, tabs = five
    assert result["validated"] and list(tabs) == ["text", "image", "video", "speech", "decisions"]
    video = tabs["video"]
    assert video["default"] == {"metric": ARENA_METRIC, "basis": "video_output|per_second", "scope": "all"}
    view = video["views"][f"{ARENA_METRIC}|video_output|per_second|all"]
    assert sorted(video["offers"][i]["id"] for i in view["valid"]) == ["bytedance/seedance-2.0", "google/veo-3.1", "kwaivgi/kling-v3.0-pro"]
    assert not entry(video, "google/veo-3.1")["free"]
    with open(space.builds / capture_id / "text.csv", encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["offer_id"] == "anthropic/claude-sonnet-5.5"]
    assert rows and {r["latency_s"] for r in rows} == {"0.994"} and {r["latency_display"] for r in rows} == {"0.994 s p50, Amazon Bedrock"}
    assert "<th>Latency</th>" in (space.builds / capture_id / "pareto.html").read_text(encoding="utf-8")


def test_a_429_stops_that_source_and_the_build_still_runs(tmp_path):
    space = Space(tmp_path)
    space.init()

    def limited(url):
        if "/stats/endpoint?" in url:
            raise ParetoError(f"HTTP 429 from {url}", "http_error", 4, status=429)
        return fixture_get(url)

    result = fetch(space, get=limited, delay=0)
    assert result["stats"]["error"] == 1 and result["stats"]["skipped"] == 438 and result["stats"]["ok"] == 0
    assert result["arena"]["ok"] == 6 and list(result["stopped"]) == ["stats"]
    built = build(space, result["capture_id"])
    assert built["validated"] and any(w.startswith("stats route stopped (HTTP 429 from ") and "438 models were not requested" in w
                                      for w in built["warnings"])
