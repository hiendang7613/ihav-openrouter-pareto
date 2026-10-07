"""Public, key-free GETs of the OpenRouter catalog and typed endpoint prices into captures/<capture_id>/."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from . import ParetoError, __version__
from .space import Space, iso, sha256_file, utc_now, write_json

Getter = Callable[[str], bytes]


def http_get(url: str, timeout: float = 30.0) -> bytes:
    """Plain GET with no credentials; any HTTP or network failure becomes a ParetoError."""
    request = urllib.request.Request(url, headers={"User-Agent": f"ihav-openrouter-pareto/{__version__}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        exc.close()
        raise ParetoError(f"HTTP {exc.code} from {url}", "http_error", 4) from None
    except (urllib.error.URLError, OSError) as exc:
        raise ParetoError(f"network error for {url}: {exc}", "network_error", 4) from None


def file_name(model_id: str) -> str:
    return "endpoints_" + urllib.parse.quote(model_id, safe="") + ".json"


def models_in(rows: list, modality: str) -> list[str]:
    return [r["id"] for r in rows if modality in r.get("architecture", {}).get("output_modalities", [])]


def fetch(space: Space, get: Getter = http_get, delay: float | None = None, now: dt.datetime | None = None) -> dict:
    """Write a new capture; the catalog must succeed, a failed endpoint is recorded and skipped."""
    config = space.config()
    moment = now or utc_now()
    capture_id = space.new_capture_id(moment)
    temporary = space.captures / f".tmp-{capture_id}"
    temporary.mkdir(parents=True)
    try:
        url = config["api"]["models_url"]
        body = get(url)
        rows = json.loads(body)["data"]
        (temporary / "api_all.json").write_bytes(body)
        manifest = {
            "schema": 1,
            "capture_id": capture_id,
            "created_at": iso(moment),
            "plugin_version": __version__,
            "field_sources": config["field_sources"],
            "api": {"url": url, "file": "api_all.json", "sha256": sha256_file(temporary / "api_all.json"), "fetched_at": iso(utc_now()), "rows": len(rows)},
            "endpoints": [],
            "tables": {},
        }
        pause = config["api"].get("request_delay_s", 0) if delay is None else delay
        for modality, template in config["api"].get("endpoints_url", {}).items():
            if modality not in config["modalities"]:
                continue
            for model_id in models_in(rows, modality):
                manifest["endpoints"].append(_fetch_endpoint(get, template, modality, model_id, temporary))
                time.sleep(pause)
        write_json(temporary / "manifest.json", manifest)
        os.replace(temporary, space.capture_dir(capture_id))
    except (ValueError, KeyError, TypeError) as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        raise ParetoError(f"catalog answer has an unexpected shape: {exc}", "bad_catalog", 4) from None
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    failed = [e["model"] for e in manifest["endpoints"] if e["error"]]
    return {"capture_id": capture_id, "path": str(space.capture_dir(capture_id)), "models": len(rows), "endpoints_ok": len(manifest["endpoints"]) - len(failed), "endpoints_failed": failed}


def _fetch_endpoint(get: Getter, template: str, modality: str, model_id: str, folder) -> dict:
    url = template.format(id=urllib.parse.quote(model_id, safe="/:"))
    entry = {"model": model_id, "modality": modality, "url": url, "file": None, "sha256": None, "error": None}
    try:
        body = get(url)
        json.loads(body)
    except ParetoError as exc:
        entry["error"] = str(exc)
        return entry
    except ValueError:
        entry["error"] = "answer is not JSON"
        return entry
    path = folder / file_name(model_id)
    path.write_bytes(body)
    entry.update(file=path.name, sha256=sha256_file(path))
    return entry
