"""Project state under ./.ihav_space/ihav-openrouter-pareto (plan section 9)."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from . import ParetoError

SPACE_DIR = Path(".ihav_space") / "ihav-openrouter-pareto"
TABLE_URL = "https://openrouter.ai/models?order=top-weekly&output_modalities={}"

DEFAULT_CONFIG = {
    "schema": 1,
    "modalities": ["text", "image", "speech"],
    "api": {
        "models_url": "https://openrouter.ai/api/v1/models?output_modalities=all",
        # Typed per-unit prices; other modalities can be added when OpenRouter documents an equivalent route.
        "endpoints_url": {"image": "https://openrouter.ai/api/v1/images/models/{id}/endpoints"},
        "request_delay_s": 0.2,
    },
    "table_urls": {
        "text": TABLE_URL.format("text"),
        "image": TABLE_URL.format("image"),
        "speech": TABLE_URL.format("speech"),
        "all": "https://openrouter.ai/models?order=top-weekly",
    },
    "field_sources": {
        "id, name, created, context_length, canonical_slug, alias_target": "api",
        "pricing (USD per token, shown per 1M tokens)": "api",
        "typed per-unit price (billable, unit, cost_usd)": "endpoints",
        "aa.intelligence_index, aa.coding_index, aa.agentic_index": "api",
        "da.<arena>/<category>.elo": "api",
        "usage.weekly_tokens, perf.latency_s, perf.throughput_tps": "table",
        "displayed price labels (from, N% off)": "table",
    },
    "price_components": {
        "text": ["input", "output"],
        "image": ["output_image", "image_output", "input", "output"],
        "speech": ["input", "output", "audio_output"],
    },
    "default_metric": {"text": "aa.intelligence_index", "image": "usage.weekly_tokens", "speech": "usage.weekly_tokens"},
    "routers": {
        "openrouter/auto": "router: picks another model per request; price -1",
        "openrouter/auto-beta": "router: picks another model per request; price -1",
        "openrouter/fusion": "router: combines other models; price -1",
        "openrouter/pareto-code": "router: picks another model per request; price -1",
        "openrouter/bodybuilder": "router: builds requests for other models; price -1",
        "typesafe/jev-router": "router: picks another model per request; price -1",
        "nvidia/switchyard": "router: picks another model per request; price -1",
    },
}

SPACE_README = """# ihav-openrouter-pareto state

Created by the ihav-openrouter-pareto plugin. Safe to delete; `fetch` and the skill's Table step rebuild it.

- `config.json`: modalities, source URLs, field-to-source map, router list, price components per chart.
- `captures/<capture_id>/`: raw public API answers, typed endpoint prices, pasted Table text and `manifest.json`.
- `builds/<capture_id>/`: `offers.json`, `<modality>.csv`, `pareto.html` made from one capture.
- `latest`: points to the last build that passed validation; a failed build leaves it unchanged.
- `history.jsonl`: one line per capture, offer, metric and price basis; rebuilding a capture adds no duplicate.
"""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_text(value) -> str:
    """Decimals in positional form (`str()` would give `3E+1` or `7.5E-7`); anything else through `str()`."""
    return format(value, "f") if isinstance(value, Decimal) else str(value)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=as_text) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Space:
    def __init__(self, project: Path | str = "."):
        self.root = Path(project) / SPACE_DIR
        self.captures = self.root / "captures"
        self.builds = self.root / "builds"
        self.config_path = self.root / "config.json"
        self.history_path = self.root / "history.jsonl"
        self.latest_path = self.root / "latest"

    def init(self) -> list[str]:
        """Create the tree and default files; never overwrite an existing file."""
        created = []
        for folder in (self.captures, self.builds):
            if not folder.is_dir():
                folder.mkdir(parents=True)
                created.append(str(folder))
        for path, text in ((self.config_path, json.dumps(DEFAULT_CONFIG, indent=1) + "\n"), (self.root / "README.md", SPACE_README)):
            if not path.exists():
                path.write_text(text, encoding="utf-8")
                created.append(str(path))
        return created

    def config(self) -> dict:
        if not self.config_path.is_file():
            raise ParetoError(f"no config at {self.config_path}; run `init` first", "not_initialised", 2)
        merged = copy.deepcopy(DEFAULT_CONFIG)
        merged.update(read_json(self.config_path))
        return merged

    def new_capture_id(self, moment: dt.datetime) -> str:
        """UTC second stamp; a suffix keeps two captures in the same second apart."""
        base = moment.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        candidate, n = base, 1
        while (self.captures / candidate).exists() or (self.captures / f".tmp-{candidate}").exists():
            n += 1
            candidate = f"{base}-{n}"
        return candidate

    def capture_ids(self) -> list[str]:
        if not self.captures.is_dir():
            return []
        return sorted(p.name for p in self.captures.iterdir() if (p / "manifest.json").is_file())

    def resolve_capture(self, ref: str | None) -> str:
        """Accept an exact capture id, a YYYY-MM-DD date that names one capture, or None for the newest."""
        ids = self.capture_ids()
        if not ids:
            raise ParetoError("no capture yet; run `fetch` first", "no_capture", 2)
        if ref is None:
            return ids[-1]
        if ref in ids:
            return ref
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ref):
            same_day = [i for i in ids if i.startswith(ref.replace("-", ""))]
            if len(same_day) == 1:
                return same_day[0]
            if same_day:
                raise ParetoError(f"{ref} is ambiguous: {', '.join(same_day)}; pass a capture id", "ambiguous_date", 2)
        raise ParetoError(f"unknown capture {ref!r}", "unknown_capture", 2)

    def capture_dir(self, capture_id: str) -> Path:
        return self.captures / capture_id

    def manifest(self, capture_id: str) -> dict:
        return read_json(self.capture_dir(capture_id) / "manifest.json")

    def save_manifest(self, capture_id: str, manifest: dict) -> None:
        write_json(self.capture_dir(capture_id) / "manifest.json", manifest)

    def latest(self) -> str | None:
        """Capture id of the published build, from the `latest` symlink or its text-file fallback."""
        path = self.latest_path
        if path.is_symlink():
            return Path(os.readlink(path)).name
        if path.is_file():
            return Path(path.read_text(encoding="utf-8").strip()).name
        return None

    def publish_latest(self, capture_id: str) -> None:
        target = Path("builds") / capture_id
        temporary = self.root / "latest.tmp"
        if temporary.is_symlink() or temporary.exists():
            temporary.unlink()
        try:
            os.symlink(target, temporary, target_is_directory=True)
        except OSError:  # Windows without symlink rights: a one-line pointer file.
            temporary.write_text(str(target) + "\n", encoding="utf-8")
        if self.latest_path.is_dir() and not self.latest_path.is_symlink():
            shutil.rmtree(self.latest_path)
        os.replace(temporary, self.latest_path)

    def add_history(self, rows: Iterable[dict]) -> int:
        """Append rows whose key is new; the same capture built twice adds nothing."""
        key = lambda r: (r["capture_id"], r["offer"], r["metric"], r["basis"])  # noqa: E731
        seen = set()
        if self.history_path.is_file():
            for line in self.history_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    seen.add(key(json.loads(line)))
        fresh = []
        for row in rows:
            if key(row) not in seen:
                seen.add(key(row))
                fresh.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
        if fresh:
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(fresh) + "\n")
        return len(fresh)
