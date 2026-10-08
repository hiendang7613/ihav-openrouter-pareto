---
name: ihav-openrouter-pareto
description: Charts OpenRouter models as quality or weekly usage versus list price with a Pareto frontier, one tab per output modality (text, image, speech), from OpenRouter's public catalog, its model pages (Arena "Checks passed", latency, video prices) and its models Table. Use when someone asks which OpenRouter model gives the best quality or usage for its price, wants an artificialanalysis-style price chart of OpenRouter models, or wants to compare two OpenRouter captures.
---

# ihav-openrouter-pareto

Run the bundled command from the user's project folder. Replace `<skill-directory>` with the installed directory that contains this `SKILL.md`. Use `python3` on macOS/Linux or `py -3` on Windows. Every command prints one JSON object; state lives in `./.ihav_space/ihav-openrouter-pareto/`.

```bash
python3 <skill-directory>/scripts/pareto.py <command> --project .
```

```powershell
py -3 <skill-directory>/scripts/pareto.py <command> --project .
```

The user's request selects the subcommand; no subcommand means `run`.

- `run`: `init`, then `fetch`, then the Table step for each modality in `config.json`, then `build`. Give the user the `html` path from the build result and open it if they ask.
- `capture`: `init`, `fetch` and the Table step, without `build`.
- `build [capture_id]`: `build --capture <capture_id>`, or the newest capture when no id is given.
- `diff <a> <b>`: `diff <a> <b>` with two capture ids, or dates that name exactly one capture each. Items under `not_comparable` have a different metric identity or price basis; never compare them.

## Table step

This skill owns the browser step; follow [table capture](references/table-capture.md). If no browser tool is available, skip it, run `build` anyway and say: "Table step skipped: no browser tool, so Weekly Tokens and the Table's Latency and Throughput are unavailable." The build then marks those columns `unavailable` and keeps the views from the API and the model-page data (Arena "Checks passed", model-page latency).

## Rules

- Never guess a price, score, unit or model match. Report what the JSON returns.
- Announce `latest` only when `build` returns `"validated": true`. Otherwise quote its `problems` and say that `latest` stayed where it was.
- Weekly tokens measure usage, not quality; call a weekly-tokens chart "Weekly usage vs price". The image, video and speech default charts are "Checks passed vs price" (OpenRouter's public Arena score); decisions defaults to "Latency vs price", which measures speed, not quality (lower is better).
- A "from" price is a lower bound. Prices are list prices, not the cost of a task, and units are never converted. The one exception is the basis "USD per Arena task (measured)": call it a measured mean cost of n Arena tasks, never a price.
- Keep a missing host capability (no browser tool) separate from a parser or data error when you report.
- Use only the public, key-free GETs that `fetch` makes. No API key, cookie, login or paid call. If a command reports HTTP 401, 403, 429 or a network error, report the message as returned and stop; do not retry through another route. A `fetch` result with `stopped` means a model-page route got 401, 403 or 429 and was not asked again; report it with the counts.
