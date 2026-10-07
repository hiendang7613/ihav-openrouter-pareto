"""Plan 12.1: the saved public answers and Table captures are intact and agree with each other."""

from __future__ import annotations

import hashlib
import json

from fixture_build import FIXTURES
from ihav_openrouter_pareto.table import parse_table


def rows(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["data"]


def test_every_fixture_matches_its_recorded_sha256():
    listed = [line.split() for line in (FIXTURES / "SHA256SUMS").read_text().splitlines() if line.strip()]
    assert len(listed) == 8
    for digest, name in listed:
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest, name


def test_catalog_shape_and_identity():
    everything = rows("models_all.json")
    assert len(everything) == 651
    assert len({r["id"] for r in everything}) == 651 and len({r["name"] for r in everything}) == 651
    assert sum(r["pricing"]["prompt"] == "-1" for r in everything) == 7
    assert sum("alias_target" in r for r in everything) == 19
    by_modality = lambda m: sorted(r["id"] for r in everything if m in r["architecture"]["output_modalities"])  # noqa: E731
    assert by_modality("image") == sorted(r["id"] for r in rows("models_image.json"))
    assert by_modality("text") == sorted(r["id"] for r in rows("models_default.json"))


def test_table_captures_are_complete_and_join_by_exact_id():
    ids = {r["id"] for r in rows("models_all.json")}
    for name, expected in (("openrouter_table_image_2026-10-07.txt", 59), ("openrouter_table_speech_2026-10-07.txt", 23)):
        parsed, errors = parse_table((FIXTURES / name).read_text(encoding="utf-8"))
        assert (len(parsed), errors) == (expected, [])
        assert {r["slug"] for r in parsed} <= ids
    parsed, errors = parse_table((FIXTURES / "openrouter_table_all_rows.txt").read_text(encoding="utf-8"),
                                 ["index", "slug", "Weekly Tokens", "Latency", "Throughput"])
    assert errors == [] and {r["slug"] for r in parsed} == ids
