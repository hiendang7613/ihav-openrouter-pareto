"""Plan 12.5 (offline part): one self-contained page with no outbound request; HTML, CSV and JSON share one report."""

from __future__ import annotations

import copy
import csv
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from ihav_openrouter_pareto.render import ASSETS, csv_rows, render_html, write_csv

ALLOWED_URL = re.compile(r"https://openrouter\.ai/\S*|http://www\.w3\.org/2000/svg")
LOADING_TAGS = {"img", "iframe", "link", "object", "embed", "audio", "video", "source", "base", "form", "frame"}
LOADING_ATTRS = {"src", "srcset", "href", "action", "formaction", "ping", "background", "poster", "data"}
NETWORK_JS = ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "import(", "innerHTML", "outerHTML", "eval(", "document.write", "new Function")


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags, self.attrs, self.blocks, self._open = [], [], [], None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend((tag, k, v) for k, v in attrs)
        self._open = (tag, dict(attrs)) if tag in ("script", "style") else None

    def handle_endtag(self, tag):
        self._open = None

    def handle_data(self, data):
        if self._open:
            self.blocks.append((self._open[0], self._open[1], data))


def data_block(page):
    return next(text for tag, attrs, text in page.blocks if attrs.get("type") == "application/json")


def test_page_is_self_contained_and_makes_no_request(built, report):
    html_text = Path(built[2]["html"]).read_text(encoding="utf-8")
    page = Page(html_text)
    assert not LOADING_TAGS & set(page.tags)
    assert not [a for a in page.attrs if a[1].lower() in LOADING_ATTRS or a[1].lower().startswith("on")]
    csp = next(v for t, k, v in page.attrs if t == "meta" and k == "content" and "default-src" in v)
    assert "default-src 'none'" in csp
    styles = [text for tag, _, text in page.blocks if tag == "style"]
    assert styles and not any("url(" in s or "@import" in s for s in styles)
    code = [text for tag, attrs, text in page.blocks if tag == "script" and "type" not in attrs]
    assert len(code) == 1 and not [w for w in NETWORK_JS if w in code[0]]
    assert all(ALLOWED_URL.fullmatch(u) for u in re.findall(r"https?://[^\s\"'<>\\)]+", html_text))
    assert "<" not in data_block(page) and json.loads(data_block(page)) == report["report"]


def test_one_tab_per_default_modality_with_selectors(report):
    modalities = report["report"]["modalities"]
    assert [m["id"] for m in modalities] == ["text", "image", "speech"]
    for m in modalities:
        assert m["scopes"] == ["all", "standard", "batch", "free"] and m["default"]["scope"] == "all"
        assert f"{m['default']['metric']}|{m['default']['basis']}|all" in m["views"]
    defaults = {m["id"]: m["default"]["metric"] for m in modalities}
    assert defaults == {"text": "aa.intelligence_index", "image": "usage.weekly_tokens", "speech": "usage.weekly_tokens"}
    weekly = next(x for x in modalities[1]["metrics"] if x["id"] == "usage.weekly_tokens")
    assert weekly["title"] == "Weekly usage vs price"


def test_csv_and_json_carry_the_same_points_and_frontiers(built, report):
    for modality in report["report"]["modalities"]:
        with open(built[2]["csv"][modality["id"]], encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        expected = list(csv_rows(report["report"], modality))
        assert len(rows) == len(expected) > 0
        on_front = {(r["metric"], f"{r['price_component']}|{r['price_unit']}", r["offer_id"]) for r in rows if r["frontier_all"] == "yes"}
        from_views = {(k.split("|")[0], "|".join(k.split("|")[1:3]), modality["offers"][i]["id"])
                      for k, v in modality["views"].items() if k.endswith("|all") for i in v["frontier"]}
        assert on_front == from_views


def test_hostile_and_long_unicode_names_stay_data(report):
    hostile = copy.deepcopy(report["report"])
    name = "</script><img src=x onerror=alert(1)>" + "Ünïcödé 名前 " * 30
    hostile["modalities"][0]["offers"][0]["name"] = name
    page = Page(render_html(hostile))
    block = data_block(page)
    assert "</script" not in block and "<img" not in block
    assert json.loads(block)["modalities"][0]["offers"][0]["name"] == name
    assert "img" not in page.tags


def test_csv_guards_formula_like_text(tmp_path, report):
    hostile = copy.deepcopy(report["report"])
    speech = next(m for m in hostile["modalities"] if m["id"] == "speech")
    for offer in speech["offers"]:
        offer["name"] = "=HYPERLINK(\"http://x\")"
    write_csv(tmp_path / "speech.csv", hostile, speech)
    rows = list(csv.DictReader((tmp_path / "speech.csv").open(encoding="utf-8", newline="")))
    assert {r["offer_name"] for r in rows} == {"'=HYPERLINK(\"http://x\")"}
    assert all(not r["price"].startswith("'") and not r["score"].startswith("'") for r in rows)


def test_page_script_builds_links_and_text_safely():
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    assert "var ORIGIN = 'https://openrouter.ai/';" in script and "split('/').map(encodeURIComponent)" in script
    assert "textContent" in script and "innerHTML" not in script


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_page_script_parses():
    subprocess.run(["node", "--check", str(ASSETS / "app.js")], check=True)


EXPONENT = re.compile(r"-?\d+(\.\d+)?[eE][-+]?\d+")
PLAIN = re.compile(r"\d+(\.\d+)?")


def test_numbers_are_written_without_exponent_form(built, report):
    from decimal import Decimal

    from ihav_openrouter_pareto.space import as_text
    from ihav_openrouter_pareto.table import weekly_tokens

    assert (as_text(Decimal("0.00003").scaleb(6)), as_text(Decimal("0.00000075")), as_text(weekly_tokens("4.03B"))) == ("30", "0.00000075", "4030000000")

    def walk(node, key=None):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, k)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v, key)
        elif isinstance(node, str) and key not in ("raw_label", "raw"):  # raw labels keep the source text as published
            yield key, node

    assert [(k, v) for k, v in walk(report) if EXPONENT.fullmatch(v)] == []
    space = built[0]
    for line in space.history_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        assert PLAIN.fullmatch(row["price"]) and PLAIN.fullmatch(row["score"]), row
    for path in built[2]["csv"].values():
        with open(path, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert all(PLAIN.fullmatch(r["price"]) and PLAIN.fullmatch(r["score"]) for r in rows)
        assert not [c for r in rows for c in r.values() if EXPONENT.fullmatch(c)]
