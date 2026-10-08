"""Replay the saved 2026-10-07 public answers and Table captures, plus the 2026-10-08 model-page answers, as one capture, offline.

Run `python tests/fixture_build.py [project-folder]` to produce pareto.html, CSV and JSON from the fixtures.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins/ihav-openrouter-pareto/core/ihav-openrouter-pareto"
FIXTURES = ROOT / "tests/fixtures/openrouter_2026-10-07"
# Arena and endpoint-stats answers of 2026-10-08 for a few models of the 2026-10-07 catalog, by URL (README there).
PAGE_FIXTURES = ROOT / "tests/fixtures/openrouter_2026-10-08"
PAGE_URLS = json.loads((PAGE_FIXTURES / "urls.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(CORE))

from ihav_openrouter_pareto import ParetoError  # noqa: E402
from ihav_openrouter_pareto.build import build  # noqa: E402
from ihav_openrouter_pareto.fetch import fetch  # noqa: E402
from ihav_openrouter_pareto.space import DEFAULT_CONFIG, Space  # noqa: E402
from ihav_openrouter_pareto.table import ingest  # noqa: E402

# The public GETs ran at 12:36 Asia/Ho_Chi_Minh (fixture README).
FETCHED_AT = dt.datetime(2026, 10, 7, 5, 36, tzinfo=dt.timezone.utc)
SEEDREAM_URL = "https://openrouter.ai/api/v1/images/models/bytedance-seed/seedream-4.5/endpoints"
# (file, expected rows shown by the page, page URL, read time from the file header or README, columns when the file has no header)
TABLES = {
    "image": ("openrouter_table_image_2026-10-07.txt", 59, DEFAULT_CONFIG["table_urls"]["image"], "2026-10-07T14:00:00+07:00", None),
    "speech": ("openrouter_table_speech_2026-10-07.txt", 23, DEFAULT_CONFIG["table_urls"]["speech"], "2026-10-07T13:54:00+07:00", None),
    # README gives 13:54-14:10 for the Table captures; this one has no own header, so the window's end is used.
    "all": ("openrouter_table_all_rows.txt", 651, DEFAULT_CONFIG["table_urls"]["all"], "2026-10-07T14:10:00+07:00",
            ["index", "slug", "Weekly Tokens", "Latency", "Throughput"]),
}


def fixture_get(url: str) -> bytes:
    """Stand-in for the network: the saved catalog, endpoint and model-page answers; anything else is a 404."""
    if url == DEFAULT_CONFIG["api"]["models_url"]:
        return (FIXTURES / "models_all.json").read_bytes()
    if url == SEEDREAM_URL:
        return (FIXTURES / "seedream_endpoints.json").read_bytes()
    saved = PAGE_URLS.get(url, {})
    if saved.get("file"):
        return (PAGE_FIXTURES / saved["file"]).read_bytes()
    status = saved.get("status") or 404
    raise ParetoError(f"HTTP {status} from {url}", "http_error", 4, status=status)


def make_capture(project: Path, tables: dict = TABLES, now: dt.datetime = FETCHED_AT, latency: bool = True) -> tuple[Space, str]:
    space = Space(project)
    space.init()
    capture_id = fetch(space, get=fixture_get, delay=0, now=now, latency=latency)["capture_id"]
    for modality, (name, expected, url, read_at, columns) in tables.items():
        ingest(space, capture_id, modality, FIXTURES / name, url, expected, "table", read_at, columns)
    return space, capture_id


def main() -> int:
    project = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    space, capture_id = make_capture(project)
    result = build(space, capture_id)
    print(json.dumps(result, indent=1, default=str))
    return 0 if result["validated"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
