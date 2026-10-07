"""The Table text contract and `ingest` completeness checks."""

from __future__ import annotations

from decimal import Decimal

import pytest

from fixture_build import FIXTURES, make_capture
from ihav_openrouter_pareto import ParetoError
from ihav_openrouter_pareto.table import ingest, latency_seconds, parse_table, price_label, throughput, weekly_tokens

HEADER = "# Columns: slug|Model Name|Weekly Tokens|Input|Output|Context|Latency\n"


@pytest.mark.parametrize("label,value", [("4.03B", "4030000000"), ("994K", "994000"), ("31.6T", "31600000000000"), ("1T", "1000000000000"), ("12", "12")])
def test_weekly_tokens(label, value):
    assert weekly_tokens(label) == Decimal(value)


@pytest.mark.parametrize("label,value", [("163ms", "0.163"), ("29.0s", "29.0"), ("1m 4s", "64"), ("2m 14s", "134"), ("1m", "60")])
def test_latency(label, value):
    assert latency_seconds(label) == Decimal(value)


def test_throughput_and_prices():
    assert throughput("80 t/s") == 80
    assert price_label("$8") == (Decimal("8"), "exact")
    assert price_label("$0.50") == (Decimal("0.50"), "exact")
    assert price_label("from $0.04") == (Decimal("0.04"), "from")
    assert price_label("$0") == (Decimal("0"), "exact")
    assert price_label("$1,200") == (Decimal("1200"), "exact")
    for bad in ("8$", "$", "about $3", "$-1"):
        with pytest.raises(ValueError):
            price_label(bad)


def test_a_spanning_cell_is_one_price_and_shifts_later_cells():
    rows, errors = parse_table(HEADER + "a/b|A: B|2.24B|from $0.04{2}|4,096|15.1s\nc/d|C: D 50% off|1M|$8|$30|—|1m 4s\n")
    assert errors == []
    single, pair = rows
    assert single["prices"] == [{"column": "Single", "raw_label": "from $0.04", "value": Decimal("0.04"), "qualifier": "from"}]
    assert single["values"]["Latency"] == ("15.1s", Decimal("15.1"))
    assert [p["column"] for p in pair["prices"]] == ["Input", "Output"]
    assert (pair["name"], pair["discount_pct"]) == ("C: D", "50")


def test_missing_values_are_absent_not_zero():
    rows, errors = parse_table(HEADER + "a/b|A|—|—|—|—|—\n")
    assert errors == [] and rows[0]["values"] == {} and rows[0]["prices"] == []


def test_structure_changes_are_errors():
    rows, errors = parse_table(HEADER + "a/b|A|1M|$1|$2|—\nc/d|C|lots|$1|$2|—|1s\n")
    assert errors == ["line 2: 6 cells, expected 7", "line 3: weekly tokens 'lots'"]
    with pytest.raises(ParetoError):
        parse_table("a/b|A|1M\n")


def test_ingest_records_complete_and_truncated_tables(tmp_path):
    space, capture_id = make_capture(tmp_path, tables={})
    full = ingest(space, capture_id, "speech", FIXTURES / "openrouter_table_speech_2026-10-07.txt", "https://openrouter.ai/models?order=top-weekly&output_modalities=speech", 23)
    assert (full["rows_read"], full["complete"], full["filters"]) == (23, True, {"order": "top-weekly", "output_modalities": "speech"})
    lines = (FIXTURES / "openrouter_table_image_2026-10-07.txt").read_text(encoding="utf-8").splitlines()
    short = tmp_path / "image_truncated.txt"
    short.write_text("\n".join(lines[:-9]) + "\n", encoding="utf-8")
    cut = ingest(space, capture_id, "image", short, "https://openrouter.ai/models?output_modalities=image", 59)
    assert (cut["rows_read"], cut["complete"]) == (50, False)
    tables = space.manifest(capture_id)["tables"]
    assert set(tables) == {"speech", "image"} and tables["image"]["sha256"] == cut["sha256"]
    with pytest.raises(ParetoError):
        ingest(space, capture_id, "video", short, "https://openrouter.ai/models", 1)
    with pytest.raises(ParetoError):
        ingest(space, capture_id, "image", short, "https://openrouter.ai/models", 59, view="grid")
