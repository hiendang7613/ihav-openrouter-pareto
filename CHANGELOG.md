# Changelog

## 0.1.0 — 2026-10-08

- Add `init`, `fetch`, `ingest`, `build` and `diff` as one standard-library CLI with JSON output, and one `/ihav-openrouter-pareto` skill (`run | capture | build | diff`) for Claude Code and Codex.
- Fetch OpenRouter's public catalog (`output_modalities=all`) and typed per-image prices from `/api/v1/images/models/<id>/endpoints` without a key; record each answer's URL, time and SHA-256 in the capture manifest.
- Ingest the models Table text read by the skill's browser step, check rows read against the row count the page shows, and keep incomplete captures from being published.
- Key offers by the verbatim API id (`:batch` and `:free` stay separate), keep every price as a typed observation (exact Decimal, unit, component, `from`, discount, source), treat `-1` as a router sentinel and `0` as a price, and exclude routers and `~…-latest` aliases by exact id with reasons.
- Keep each Design Arena arena/category as its own metric; never merge ELO across categories.
- Compute the Pareto frontier (minimum price, maximum score) for every (modality, metric, price component and unit, offer scope) view, and check it against pairwise dominance on every subset of a 3×3 grid.
- Write one self-contained HTML page (no CDN, no outbound request, a strict Content-Security-Policy) with a tab per modality, plus CSV and JSON from the same views; move `latest` only after a validated build and append history without duplicates.
