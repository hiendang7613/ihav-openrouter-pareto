"""Plan 12.4: captures, builds, `latest`, history and diff in .ihav_space/ihav-openrouter-pareto."""

from __future__ import annotations

import json
import os

import pytest

import fixture_build
from fixture_build import FETCHED_AT, FIXTURES, TABLES, fixture_get, make_capture
from ihav_openrouter_pareto import ParetoError
from ihav_openrouter_pareto.build import build
from ihav_openrouter_pareto.diff import diff
from ihav_openrouter_pareto.fetch import fetch
from ihav_openrouter_pareto.space import DEFAULT_CONFIG, Space
from ihav_openrouter_pareto.table import ingest


def history_lines(space):
    return space.history_path.read_text(encoding="utf-8").splitlines() if space.history_path.exists() else []


def test_two_captures_on_the_same_day_get_different_ids(tmp_path):
    space, first = make_capture(tmp_path, tables={})
    _, second = make_capture(tmp_path, tables={})
    assert (first, second) == ("20261007T053600Z", "20261007T053600Z-2")
    with pytest.raises(ParetoError) as error:
        space.resolve_capture("2026-10-07")
    assert error.value.code == "ambiguous_date"
    assert space.resolve_capture(None) == second


def test_a_failed_build_keeps_the_last_published_build(tmp_path):
    space, good = make_capture(tmp_path)
    assert build(space, good)["validated"] and space.latest() == good
    before = history_lines(space)
    lines = (FIXTURES / TABLES["image"][0]).read_text(encoding="utf-8").splitlines()
    short = tmp_path / "short.txt"
    short.write_text("\n".join(lines[:40]) + "\n", encoding="utf-8")
    _, bad = make_capture(tmp_path, tables={"speech": TABLES["speech"]})
    ingest(space, bad, "image", short, TABLES["image"][2], 59)
    result = build(space, bad)
    assert not result["validated"] and result["problems"] == ["table_image: 37 of 59 expected rows, 0 parse errors"]
    assert space.latest() == good and history_lines(space) == before
    assert (space.builds / bad / "pareto.html").is_file()
    image = next(m for m in json.loads((space.builds / bad / "offers.json").read_text())["report"]["modalities"] if m["id"] == "image")
    assert image["views"]["usage.weekly_tokens|image_output|per_m_tokens|all"]["excluded"]["capture_incomplete"] > 0


def test_a_table_file_changed_after_ingest_blocks_publication(tmp_path):
    space, capture_id = make_capture(tmp_path, tables={"speech": TABLES["speech"]})
    path = space.capture_dir(capture_id) / "table_speech.txt"
    path.write_text(path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    result = build(space, capture_id)
    assert result["problems"] == ["table_speech: file changed after ingest"] and space.latest() is None


def test_rebuilding_adds_no_duplicate_history(tmp_path):
    space, capture_id = make_capture(tmp_path)
    first = build(space, capture_id)
    assert first["history_rows_added"] > 1000
    lines = history_lines(space)
    assert build(space, capture_id)["history_rows_added"] == 0 and history_lines(space) == lines
    keys = [(r["capture_id"], r["offer"], r["metric"], r["basis"]) for r in map(json.loads, lines)]
    assert len(keys) == len(set(keys))


def test_api_only_build_marks_table_columns_unavailable(tmp_path):
    space, capture_id = make_capture(tmp_path, tables={})
    result = build(space, capture_id)
    assert result["validated"]
    image = next(m for m in json.loads((space.builds / capture_id / "offers.json").read_text())["report"]["modalities"] if m["id"] == "image")
    weekly = next(m for m in image["metrics"] if m["id"] == "usage.weekly_tokens")
    assert weekly["status"] == "unavailable" and "browser step not run" in weekly["reason"]
    assert result["views"]["image"]["default"]["metric"] == "arena.checks_passed_pct"
    assert not any(k.startswith("usage.") for k in image["views"])


def test_latest_falls_back_to_a_pointer_file_without_symlinks(tmp_path, monkeypatch):
    space, capture_id = make_capture(tmp_path, tables={})

    def no_symlink(*args, **kwargs):
        raise OSError("symlinks not permitted")

    monkeypatch.setattr(os, "symlink", no_symlink)
    build(space, capture_id)
    assert space.latest_path.is_file() and not space.latest_path.is_symlink() and space.latest() == capture_id


def test_diff_compares_only_the_same_identity_and_refuses_the_rest(tmp_path):
    space, a = make_capture(tmp_path)
    catalog = json.loads((FIXTURES / "models_all.json").read_text(encoding="utf-8"))
    catalog["data"] = [r for r in catalog["data"] if r["id"] != "openai/gpt-image-2"]
    for row in catalog["data"]:
        if row["id"] == "anthropic/claude-sonnet-5.5":
            row["pricing"]["prompt"] = "0.0000025"
    changed = json.dumps(catalog).encode()
    get = lambda url: changed if url == DEFAULT_CONFIG["api"]["models_url"] else fixture_get(url)  # noqa: E731
    b = fetch(space, get=get, delay=0, now=FETCHED_AT.replace(hour=9))["capture_id"]
    result = diff(space, a, b)
    assert result["offers_removed"] == ["openai/gpt-image-2"] and result["offers_added"] == []
    assert result["price_changes"] == [{"offer": "anthropic/claude-sonnet-5.5", "price_basis": "input|per_m_tokens|api|prompt", "a": "2", "b": "2.5"}]
    refused = [r for r in result["not_comparable"] if r["offer"] == "openai/gpt-image-2.5-sunburst"]
    assert {r.get("metric") or r.get("price_basis") for r in refused} >= {"usage.weekly_tokens", "input|per_m_tokens|table|Input"}
    assert all(r["reason"] == "only in capture a; not comparable" for r in refused)


def test_fetch_uses_only_public_urls_and_records_endpoint_failures(tmp_path):
    space = Space(tmp_path)
    space.init()
    asked = []
    result = fetch(space, get=lambda url: asked.append(url) or fixture_get(url), delay=0, now=FETCHED_AT)
    assert asked[0] == DEFAULT_CONFIG["api"]["models_url"]
    kinds = {"https://openrouter.ai/api/v1/images/models/": [], "https://openrouter.ai/api/frontend/v1/arena/explore/models/": [],
             "https://openrouter.ai/api/frontend/v1/stats/endpoint?": []}
    for url in asked[1:]:
        kinds[next(k for k in kinds if url.startswith(k))].append(url)
    images, arena, stats = kinds.values()
    assert (len(images), len(arena), len(stats)) == (61, 82, 439) and all(u.endswith("/endpoints") for u in images)
    assert result["endpoints_ok"] == 1 and len(result["endpoints_failed"]) == 60
    assert result["arena"] == {"ok": 6, "absent": 76, "error": 0, "skipped": 0} and result["stopped"] == {}
    manifest = space.manifest(result["capture_id"])
    assert manifest["api"]["rows"] == 651 and manifest["field_sources"] == DEFAULT_CONFIG["field_sources"]


def test_a_failed_catalog_fetch_leaves_no_capture(tmp_path):
    space = Space(tmp_path)
    space.init()

    def down(url):
        raise ParetoError(f"HTTP 503 from {url}", "http_error", 4)

    with pytest.raises(ParetoError):
        fetch(space, get=down, delay=0)
    with pytest.raises(ParetoError):
        fetch(space, get=lambda url: b"<html>not json</html>", delay=0)
    assert space.capture_ids() == [] and list(space.captures.iterdir()) == []


def test_init_never_overwrites(tmp_path):
    space = Space(tmp_path)
    assert len(space.init()) == 4
    space.config_path.write_text('{"modalities": ["text"]}', encoding="utf-8")
    assert space.init() == [] and space.config()["modalities"] == ["text"]
    assert fixture_build.ROOT.joinpath(".gitignore").read_text().count(".ihav_space/") == 1
