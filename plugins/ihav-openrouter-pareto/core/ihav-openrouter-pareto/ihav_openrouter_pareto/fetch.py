"""Public, key-free GETs of the OpenRouter catalog, typed endpoint prices and model-page data into captures/<capture_id>/."""

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
from .normalize import exclusion
from .space import Space, iso, sha256_file, utc_now, write_json

Getter = Callable[[str], bytes]
Progress = Callable[[int, int, str, str], None]
# A model-page source stops at the first of these answers (plan bản 3, section 3); the build still runs with what arrived.
STOP_STATUS = (401, 403, 429)


def http_get(url: str, timeout: float = 30.0) -> bytes:
    """Plain GET with no credentials; any HTTP or network failure becomes a ParetoError."""
    request = urllib.request.Request(url, headers={"User-Agent": f"ihav-openrouter-pareto/{__version__}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        exc.close()
        raise ParetoError(f"HTTP {exc.code} from {url}", "http_error", 4, status=exc.code) from None
    except (urllib.error.URLError, OSError) as exc:
        raise ParetoError(f"network error for {url}: {exc}", "network_error", 4) from None


def file_name(model_id: str) -> str:
    return "endpoints_" + urllib.parse.quote(model_id, safe="") + ".json"


def models_in(rows: list, modality: str) -> list[str]:
    return [r["id"] for r in rows if modality in r.get("architecture", {}).get("output_modalities", [])]


def page_jobs(config: dict, rows: list, latency: bool = True) -> list[tuple[str, str, str, str]]:
    """(source, modality, permaslug, url) once per permaslug of each configured modality; routers and aliases are skipped."""
    api, jobs = config["api"], []
    for modality in config["modalities"]:
        slugs = sorted({r["canonical_slug"] for r in rows if r.get("canonical_slug") and exclusion(r, config["routers"]) is None
                        and modality in r.get("architecture", {}).get("output_modalities", [])})
        quoted = [(s, urllib.parse.quote(s, safe="/:")) for s in slugs]
        tab = config["arena_tabs"].get(modality)
        if tab:
            jobs += [("arena", modality, s, api["arena_url"].format(permaslug=q, tab=tab)) for s, q in quoted]
        perf = config["perf_workloads"].get(modality)
        if latency and perf:
            jobs += [("stats", modality, s, api["stats_url"].format(permaslug=q, workload=perf["workload"], latency_metric=perf["latency_metric"]))
                     for s, q in quoted]
    return jobs


def fetch(space: Space, get: Getter = http_get, delay: float | None = None, now: dt.datetime | None = None, latency: bool = True,
          progress: Progress | None = None) -> dict:
    """Write a new capture; the catalog must succeed, a failed endpoint or model-page answer is recorded and skipped."""
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
            "arena": [],
            "stats": [],
            "tables": {},
        }
        pause = config["api"].get("request_delay_s", 0) if delay is None else delay
        for modality, template in config["api"].get("endpoints_url", {}).items():
            if modality not in config["modalities"]:
                continue
            for model_id in models_in(rows, modality):
                manifest["endpoints"].append(_fetch_endpoint(get, template, modality, model_id, temporary))
                time.sleep(pause)
        jobs = page_jobs(config, rows, latency)
        stopped = {}
        for n, (source, modality, permaslug, url) in enumerate(jobs, 1):
            manifest[source].append(_fetch_page(get, source, modality, permaslug, url, temporary, stopped))
            if manifest[source][-1]["status"] != "skipped":
                time.sleep(pause)
            if progress:
                progress(n, len(jobs), source, permaslug)
        write_json(temporary / "manifest.json", manifest)
        os.replace(temporary, space.capture_dir(capture_id))
    except (ValueError, KeyError, TypeError) as exc:
        shutil.rmtree(temporary, ignore_errors=True)
        raise ParetoError(f"catalog answer has an unexpected shape: {exc}", "bad_catalog", 4) from None
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    failed = [e["model"] for e in manifest["endpoints"] if e["error"]]
    return {"capture_id": capture_id, "path": str(space.capture_dir(capture_id)), "models": len(rows), "endpoints_ok": len(manifest["endpoints"]) - len(failed),
            "endpoints_failed": failed, "arena": page_counts(manifest["arena"]), "stats": page_counts(manifest["stats"]), "stopped": stopped}


def page_counts(entries: list[dict]) -> dict:
    """ok, absent (the Arena has no public result for that tab), error and skipped (after a stop status)."""
    counts = {"ok": 0, "absent": 0, "error": 0, "skipped": 0}
    for entry in entries:
        counts[entry["status"]] += 1
    return counts


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


def _fetch_page(get: Getter, source: str, modality: str, permaslug: str, url: str, folder, stopped: dict) -> dict:
    entry = {"modality": modality, "permaslug": permaslug, "url": url, "file": None, "sha256": None, "fetched_at": None,
             "status": "skipped", "http_status": None, "error": None}
    if source in stopped:
        entry["error"] = f"not requested: {stopped[source]}"
        return entry
    entry["fetched_at"] = iso(utc_now())
    try:
        body = get(url)
        json.loads(body)
    except ParetoError as exc:
        entry["http_status"] = exc.status
        if source == "arena" and exc.status == 404:  # "Model has no public Arena results on this tab"
            entry["status"] = "absent"
            return entry
        entry["status"], entry["error"] = "error", str(exc)
        if exc.status in STOP_STATUS:
            stopped[source] = f"{source} stopped after {exc}"
        return entry
    except ValueError:
        entry["status"], entry["error"] = "error", "answer is not JSON"
        return entry
    path = folder / f"{source}_{modality}_{urllib.parse.quote(permaslug, safe='')}.json"
    path.write_bytes(body)
    entry.update(file=path.name, sha256=sha256_file(path), status="ok")
    return entry
