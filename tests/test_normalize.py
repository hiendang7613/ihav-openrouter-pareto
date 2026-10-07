"""Plan 12.2: identity, typed prices (units, from, discount, 0, -1, missing), metric identities and exclusions."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from ihav_openrouter_pareto import ParetoError
from ihav_openrouter_pareto.fetch import fetch
from ihav_openrouter_pareto.normalize import load_capture, select_price
from ihav_openrouter_pareto.space import DEFAULT_CONFIG, Space
from ihav_openrouter_pareto.table import ingest

HEADER = "# Columns: slug|Model Name|Weekly Tokens|Input|Output|Latency\n"


def model(model_id, prompt="0.000001", completion="0.000002", modality="image", **extra):
    row = {"id": model_id, "name": extra.pop("name", model_id), "architecture": {"output_modalities": [modality]},
           "pricing": {"prompt": prompt, "completion": completion}}
    row.update(extra)
    return row


def synthetic(tmp_path, rows, endpoints=None, table=None):
    """A capture made through the real fetch and ingest code from in-memory answers."""
    endpoints = endpoints or {}

    def get(url):
        if url == DEFAULT_CONFIG["api"]["models_url"]:
            return json.dumps({"data": rows}).encode()
        for model_id, doc in endpoints.items():
            if url.endswith(f"/{model_id}/endpoints"):
                return json.dumps(doc).encode()
        raise ParetoError("HTTP 404", "http_error", 4)

    space = Space(tmp_path)
    space.init()
    capture_id = fetch(space, get=get, delay=0)["capture_id"]
    if table is not None:
        path = tmp_path / "table.txt"
        path.write_text(HEADER + table, encoding="utf-8")
        ingest(space, capture_id, "image", path, DEFAULT_CONFIG["table_urls"]["image"], len(table.strip().splitlines()))
    catalog = load_capture(space.capture_dir(capture_id), space.config())
    return {o["id"]: o for o in catalog["offers"]}, catalog


@pytest.fixture(scope="module")
def real(built):
    space, capture_id, _ = built
    return {o["id"]: o for o in load_capture(space.capture_dir(capture_id), space.config())["offers"]}


def prices(offer, source=None):
    return [p for p in offer["prices"] if source is None or p["source"] == source]


def by_column(offer, column):
    return next(p for p in offer["prices"] if p["column"] == column)


def test_standard_batch_and_free_offers_stay_separate_with_their_own_prices(real):
    standard, batch = real["anthropic/claude-sonnet-5.5"], real["anthropic/claude-sonnet-5.5:batch"]
    assert (standard["variant"], batch["variant"]) == ("standard", "batch")
    assert by_column(standard, "prompt")["value"] == Decimal("2") and by_column(batch, "prompt")["value"] == Decimal("1")
    assert real["fish-audio/s2.1-pro-free:free"]["variant"] == "free"


def test_api_prices_are_exact_decimals_per_million_tokens(real):
    seedream = real["bytedance-seed/seedream-4.5"]
    image_output = by_column(seedream, "image_output")
    assert (image_output["raw_label"], image_output["value"], image_output["unit"]) == ("0.00000958083832335329", Decimal("9.58083832335329"), "per_m_tokens")
    # The catalog's per-token image_output is never used as a per-image price.
    assert select_price(seedream, "image_output", "per_image") is None


def test_typed_endpoint_price_per_image_and_table_from_label(real):
    seedream = real["bytedance-seed/seedream-4.5"]
    endpoint = by_column(seedream, "endpoint:seed")
    assert (endpoint["component"], endpoint["unit"], endpoint["value"]) == ("output_image", "per_image", Decimal("0.04"))
    label = by_column(seedream, "Single")
    assert (label["raw_label"], label["qualifier"], label["unit"], label["component"]) == ("from $0.04", "from", "per_image", "output_image")
    chosen, lower_bound = select_price(seedream, "output_image", "per_image")
    assert chosen["source"] == "table" and lower_bound is True


def test_two_price_columns_take_the_unit_of_an_equal_api_price(real):
    sunburst = real["openai/gpt-image-2.5-sunburst"]
    assert [(p["column"], p["component"], p["unit"]) for p in prices(sunburst, "table")] == [
        ("Input", "input", "per_m_tokens"), ("Output", "image_output", "per_m_tokens")]
    # A label with no equal structured price keeps an unknown unit and is never plotted.
    audio = by_column(real["bytedance-seed/seed-audio-1-0"], "Single")
    assert (audio["unit"], audio["unit_from"]) == ("unknown", "no equal structured price")


def test_discount_is_recorded_once_and_never_applied_again(real):
    flux = by_column(real["black-forest-labs/flux-3-image"], "Single")
    assert (flux["value"], flux["discount_pct"], flux["qualifier"]) == (Decimal("0.0205"), "50", "from")


def test_discounted_exact_label(tmp_path):
    offers, _ = synthetic(tmp_path, [model("x/y", prompt="0.000004", completion="0.000004")], table="x/y|X: Y 50% off|1M|$4|$4|1s\n")
    label = by_column(offers["x/y"], "Input")
    assert (label["qualifier"], label["discount_pct"], label["value"], label["unit"]) == ("discounted", "50", Decimal("4"), "per_m_tokens")


def test_zero_minus_one_and_missing(real, tmp_path):
    free = real["inclusionai/ming-image-0.1-design"]
    assert all(p["value"] == 0 for p in prices(free) if p["status"] == "ok")
    kokoro = real["hexgrad/kokoro-82m"]
    assert by_column(kokoro, "completion")["value"] == 0 and by_column(kokoro, "prompt")["value"] == Decimal("0.62")
    router = real["openrouter/auto"]
    assert router["excluded"]["reason"] == "router"
    assert {p["status"] for p in prices(router)} == {"sentinel"} and all(p["value"] is None for p in prices(router))
    offers, catalog = synthetic(tmp_path, [model("a/new-router", prompt="-1", completion="-1"), model("a/b", completion="-0.5")],
                                table="a/b|a/b|—|—|—|—\n")
    assert offers["a/new-router"]["excluded"] == {"reason": "router", "detail": "price -1 sentinel; id is not in the router list"}
    assert catalog["warnings"] == ["a/new-router has price -1 but is not in the router list; excluded as a router"]
    assert by_column(offers["a/b"], "completion")["status"] == "invalid"
    assert prices(offers["a/b"], "table") == [] and "usage.weekly_tokens" not in offers["a/b"]["metrics"]


def test_megapixel_unit_from_a_typed_endpoint(tmp_path):
    doc = {"endpoints": [{"provider_slug": "p", "pricing": [{"billable": "output_image", "unit": "megapixel", "cost_usd": 0.03}]}]}
    offers, _ = synthetic(tmp_path, [model("bfl/flux", prompt="0", completion="0")], endpoints={"bfl/flux": doc})
    price = by_column(offers["bfl/flux"], "endpoint:p")
    assert (price["unit"], price["value"]) == ("per_megapixel", Decimal("0.03"))


def test_routers_and_aliases_by_exact_id_and_relace_stays(real):
    excluded = {i: o["excluded"]["reason"] for i, o in real.items() if o["excluded"]}
    assert sorted(i for i, r in excluded.items() if r == "router") == sorted(DEFAULT_CONFIG["routers"])
    assert sum(r == "alias" for r in excluded.values()) == 19
    assert "~typesafe/jev-latest" in real["typesafe/jev-1.13"]["aliases"]
    assert real["relace/relace-apply-3"]["excluded"] is None and real["relace/relace-search"]["excluded"] is None


def test_design_arena_categories_are_separate_metric_identities(real):
    opus = real["anthropic/claude-opus-5.5"]["metrics"]
    assert opus["da.models/3d.elo"]["value"] == 1492 and opus["da.agents/mobileapps.elo"]["value"] == 1328
    assert real["anthropic/claude-opus-5"]["metrics"]["da.agents/mobileapps.elo"]["value"] == 1348
    assert not any(k.startswith("da.") and "/" not in k for k in opus)


def test_table_joins_by_id_then_unique_name_else_unmatched(tmp_path):
    rows = [model("p/one", name="P: One"), model("p/two", name="P: Two")]
    offers, _ = synthetic(tmp_path, rows, table="p/one|P: One|5M|—|—|1s\n|P: Two|7M|—|—|2s\nq/ghost|Q: Ghost|9M|$1|$2|3s\n")
    assert offers["p/one"]["table"]["match"] == "id" and offers["p/two"]["table"]["match"] == "name"
    ghost = offers["q/ghost"]
    assert ghost["match"] == "unmatched" and ghost["metrics"]["usage.weekly_tokens"]["value"] == Decimal("9000000")
    assert prices(ghost, "api") == [] and {p["unit"] for p in prices(ghost)} == {"unknown"}


def test_pricing_overrides_stay_raw_and_are_not_observations(real):
    tiered = real["openai/gpt-6.1-sol-pro"]
    assert not any(p["column"] == "overrides" for p in tiered["prices"])
    assert by_column(tiered, "prompt")["value"] == Decimal("2")
