# Changelog

## Unreleased

- Add `scripts/charts.py`: one command, no LLM and no browser, with tabs for text, image, video, speech and decisions; `--offline` replays the fixtures.
- Fetch two public routes of the model page per model (plan bản 3): Arena "Checks passed" (`arena.checks_passed_pct`, image, video and speech) and p50 latency per provider (`stats.latency_p50_s`, with the page's workload and latency metric per modality). An Arena 404 is recorded as `absent`; an HTTP 401, 403 or 429 stops that route and the build runs with what arrived. `fetch --no-latency` skips the latency route.
- Chart video against the model page's per-second list prices (the lowest SKU or tier as a "from" lower bound); catalog video prices are `0`.
- Default image, video and speech charts are "Checks passed vs price"; latency is a table column, a hover line and CSV columns (`latency_s`, `latency_display`, `table_latency_s`).
- Chart latency against price in every tab (plan bản 4): metrics record `better: higher | lower`, and a lower-is-better frontier is the minimum price and minimum latency. Decisions defaults to "Latency vs price".
- Add the measured Arena cost per task (mean `costUsd` of the model's scored tasks, with n) as a column, a hover line, CSV columns (`arena_cost_per_task_usd`, `arena_cost_n`) and a selectable x axis labelled "measured, not a list price"; it is never a default and never makes an offer paid or free.
- Leave video-input SKUs out of the video per-second "from" price, and read Arena and stats answers as exact Decimals.
- `diff` reports the measured Arena cost per task under its own key, `measured_cost_changes`, apart from `price_changes`.
- `scripts/charts.py` prints a short summary and opens the page by default; `--json` prints the full result, `--no-open` skips the browser.

## 0.1.0 — 2026-10-08

- Add `init`, `fetch`, `ingest`, `build` and `diff` as one standard-library CLI with JSON output, and one `/ihav-openrouter-pareto` skill (`run | capture | build | diff`) for Claude Code and Codex.
- Fetch OpenRouter's public catalog (`output_modalities=all`) and typed per-image prices from `/api/v1/images/models/<id>/endpoints` without a key; record each answer's URL, time and SHA-256 in the capture manifest.
- Ingest the models Table text read by the skill's browser step, check rows read against the row count the page shows, and keep incomplete captures from being published.
- Key offers by the verbatim API id (`:batch` and `:free` stay separate), keep every price as a typed observation (exact Decimal, unit, component, `from`, discount, source), treat `-1` as a router sentinel and `0` as a price, and exclude routers and `~…-latest` aliases by exact id with reasons.
- Keep each Design Arena arena/category as its own metric; never merge ELO across categories.
- Compute the Pareto frontier (minimum price, maximum score) for every (modality, metric, price component and unit, offer scope) view, and check it against pairwise dominance on every subset of a 3×3 grid.
- Write one self-contained HTML page (no CDN, no outbound request, a strict Content-Security-Policy) with a tab per modality, plus CSV and JSON from the same views; move `latest` only after a validated build and append history without duplicates.
