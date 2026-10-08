# ihav-openrouter-pareto

OpenRouter models as quality or weekly usage versus list price, with a Pareto frontier, inside Claude Code and Codex.

One build gives one self-contained HTML page (no CDN, no outbound request) with a tab per output modality (text, image, speech), plus a CSV per modality and one JSON file, all from the same observations and frontiers.

Status: 0.1.0, unreleased. Plan approved 2026-10-07 13:21 (ai-image_tools/ai-image-studio/labs/plans/openrouter_pareto_plugin_plan.md, bản 2, SHA-256 `698866c5…`); its bản 3 delta (`openrouter_pareto_plan_v3_delta.md`, SHA-256 `e76d39fd…`: Arena "Checks passed", model-page latency, video prices per second) approved 2026-10-08 11:42; its bản 4 delta (`openrouter_pareto_plan_v4_delta.md`, SHA-256 `f9cf9c06…`: latency vs price, measured Arena cost per task, no video-input SKUs) approved 2026-10-08 12:51. Not yet published to the ihav catalog.

## Install

Requires Python 3.9 or later. The core uses only the Python standard library. It needs no API key, account or paid service.

Claude Code, from a local checkout:

```bash
claude plugin marketplace add /path/to/ihav-openrouter-pareto
claude plugin install ihav-openrouter-pareto@ihav-openrouter-pareto
```

Codex, from a local checkout:

```bash
codex plugin marketplace add /path/to/ihav-openrouter-pareto
codex plugin add ihav-openrouter-pareto@ihav-openrouter-pareto
```

Restart the host, then type `/ihav-openrouter-pareto` in Claude Code, or ask Codex to "build the OpenRouter Pareto charts".

## Use

| Skill subcommand | What it does |
|---|---|
| `run` (default) | `init`, `fetch`, the browser Table step for each modality, `build`, then gives the HTML path |
| `capture` | `init`, `fetch` and the Table step, without a build |
| `build [capture_id]` | builds the given capture, or the newest one |
| `diff <a> <b>` | price and metric changes, new and removed offers between two captures; measured Arena cost changes apart, under `measured_cost_changes` |

The skill owns the browser step: it opens `https://openrouter.ai/models?order=top-weekly&output_modalities=<m>`, switches to the Table view, reads the rows and hands the text to `ingest` ([contract](plugins/ihav-openrouter-pareto/core/ihav-openrouter-pareto/references/table-capture.md)). Without a browser tool, `build` still runs from the API and model-page data and marks the Table's Weekly Tokens, Latency and Throughput `unavailable`.

The same commands work from a terminal; each prints one JSON object:

```bash
CLI=plugins/ihav-openrouter-pareto/core/ihav-openrouter-pareto/scripts/pareto.py
python3 $CLI init --project .
python3 $CLI fetch --project .            # --no-latency skips the model-page latency route
python3 $CLI ingest --project . --modality image --file table_image.txt \
  --url "https://openrouter.ai/models?order=top-weekly&output_modalities=image" --expected-rows 59
python3 $CLI build --project .
python3 $CLI diff --project . 20261007T053600Z 20261008T020000Z
```

Exit codes: `0` success, `2` usage or missing state, `3` incomplete Table or build not validated, `4` network or HTTP failure, `1` other errors.

One command without an LLM or a browser, from a checkout (tabs: text, image, video, speech, decisions; `--modalities` changes them):

```bash
python3 scripts/charts.py --offline   # seconds, no network: the saved 2026-10-07 answers and Tables, 2026-10-08 model-page answers
python3 scripts/charts.py             # live: init, enable the tabs in config.json, fetch, build
```

Each run prints a short summary (each tab's valid / total offers and default view, then the page path) and opens the page in the default browser. `--json` prints the full result as one JSON object instead, `--no-open` leaves the browser alone, and `--project <folder>` puts the state somewhere other than the current folder.

A live run on 2026-10-08 made 675 public GETs (catalog 1, image endpoints 61, Arena 121, latency 492) in 9 min 26 s and prints its progress on stderr; `--no-latency` drops the latency requests. It has no Table, so Weekly Tokens and the Table's Latency and Throughput are `unavailable`. Image, video and speech chart "Checks passed vs price"; text charts the Intelligence Index; decisions has no public quality metric, so it charts "Latency vs price" (speed, not quality).

## What the page shows

- A tab per modality in `config.json` (default text, image, speech; `scripts/charts.py` adds video and decisions).
- A selector of one metric, one price component with its unit, and one offer scope (`all`, `standard`, `batch`, `free`). Every part of the view follows that one selection: points, axes, the "n valid / N total" count, the reasons for exclusion, the frontier, hover and the table.
- Default views: text uses the Artificial Analysis Intelligence Index; image, video and speech use "Checks passed vs price"; decisions uses "Latency vs price". The default price is the list-price component and unit with the most valid offers for that metric; the measured Arena cost is never a default.
- Latency (model page or Table) can be chosen as the chart metric in every tab. Lower is better there: the frontier is the minimum price and minimum latency, and the step line is the lowest latency observed at a price up to that point. The y axis is log scale, with slower points higher.
- The table has a Latency column (model-page p50 and, with a Table, the Table's latency, each labelled with its source) and an "Arena cost / task" column (measured mean and its n); hover shows both.
- The x axis is a log scale of positive prices; price 0 sits in its own band on the left. The step line is the best score observed at a price up to that point; it does not stand for an intermediate model.
- Symbols: a circle is an exact price, a diamond a "from" price (a lower bound), a square a free offer, a hollow mark a 0 price inside a paid offer. Colours mark standard, batch and `:free` offers.

## Data rules

- **Sources.** Only OpenRouter. The public catalog (`/api/v1/models?output_modalities=all`) gives ids, names, prices and benchmarks; `/api/v1/images/models/<id>/endpoints` gives typed per-image or per-megapixel prices; the models Table gives Weekly Tokens, Latency, Throughput and the displayed price labels. Two public routes that the model page reads, keyed by the catalog's `canonical_slug` (permaslug), give the rest: `/api/frontend/v1/arena/explore/models/<permaslug>?tab=<image|video|speech>` ("Checks passed") and `/api/frontend/v1/stats/endpoint?permaslug=…&perfWorkload=…&latencyMetric=…` (p50 latency per provider and the video list prices). `config.json` and each capture manifest record which field comes from which source. An Arena 404 means "no public Arena result" and is recorded as `absent`; an HTTP 401, 403 or 429 stops that route for the rest of the fetch, and the build runs with what arrived.
- **Identity.** An offer is the verbatim API id, so `:batch` and `:free` offers stay separate. A Table row joins by its model link (the exact id), else by a unique full display name; otherwise it stays `unmatched` and gets no API price.
- **Prices.** Every price is kept as an observation: column, raw label, exact Decimal value, unit, component, qualifier (`exact`, `from`, `discounted`), discount, source and capture id. Catalog prices are USD per token and are shown per 1M tokens (an exact decimal shift). `-1` is a router sentinel, never a price. `0` is a valid price. Values are compared exactly; rounding happens only on display.
- **Table price units.** The Table text carries no unit. A label takes the unit of the one API or endpoint price of the same offer with an equal value; otherwise its unit is `unknown` and it is not plotted. A displayed discount is recorded and never applied again.
- **One price per chart.** A chart uses one component and one unit. Units are never converted. For one offer, a Table label confirmed this way is preferred, then a typed endpoint price, then the catalog price.
- **Measured Arena cost (the one exception to list prices).** The basis `arena_task · USD per Arena task (measured mean, not a list price)` is the mean `costUsd` of the model's own scored Arena tasks, with its n. It can be chosen as the x axis in image, video and speech, never by default, so models priced per image, per megapixel, per token or per second compare on one measured unit without converting any list price. Each model's task set can differ slightly, and a video task is one clip at the Arena's own length and resolution. It never makes an offer paid or free; on 2026-10-08 seedream-4.5's mean (0.04) equalled its per-image list price.
- **Metrics.** `aa.intelligence_index`, `aa.coding_index`, `aa.agentic_index`, `da.<arena>/<category>.elo` (one identity per arena and category; ELO is never merged across categories), `usage.weekly_tokens`, `perf.throughput_tps`, `perf.latency_s`, `arena.checks_passed_pct` (Arena `checksPassed / checksTotal × 100`, image, video and speech; 0 checks run gives no score) and `stats.latency_p50_s` (the lowest provider p50 over the 30 minutes before the fetch; time to first token for text, generation time for image and video, full response for speech and decisions). A missing score is not plotted and never counts as 0. Weekly tokens measure usage, not quality. An Arena score rates the model, so every offer of that model gets it; model-page latency is read for `variant=standard`, so only the offer without a `:` suffix gets it. Latency metrics are `lower` is better (each metric records `better: higher | lower`); every other metric is higher is better.
- **Exclusions.** Routers by exact id (the seven `-1` rows of 2026-10-07, listed in `config.json`), any other `-1` row, and `~…-latest` aliases (shown as aliases of their target). `relace/relace-apply-3` and `relace/relace-search` are models and stay. Raw rows always stay in the capture.
- **Long-context tiers** (`pricing.overrides`) stay in the raw capture; charts use the base price.
- **Video prices.** Catalog token prices of video models are `0`, so video uses the model page's per-second list prices (`video_output · USD per second`). Each SKU and resolution tier is an observation, except video-input SKUs (a different task); the lowest is shown as a "from" lower bound. Other units (per megapixel-second, per 1M tokens) stay in the capture and are not plotted.
- **Speech units.** The catalog reports speech prices in its per-token fields; the page shows the unit the API states. A provider may bill characters or seconds instead.

## State

```
./.ihav_space/ihav-openrouter-pareto/
  README.md  config.json
  captures/<capture_id>/   manifest.json, api_all.json, endpoints_<id>.json, arena_<modality>_<permaslug>.json,
                           stats_<modality>_<permaslug>.json, table_<modality>.txt
  builds/<capture_id>/     offers.json, <modality>.csv, pareto.html
  latest -> builds/<capture_id>   moved only after a validated build (a one-line text file where symlinks are not allowed)
  history.jsonl            one line per capture, offer, metric and price basis; rebuilding adds no duplicate
```

A capture id is the UTC second of the fetch (`20261007T053600Z`); a second capture in the same second gets `-2`. `diff` and `build` also accept a date when exactly one capture has it. A build validates only when every ingested Table has all expected rows and parses, no Table file changed after ingest, and the page, CSV and JSON carry the same report.

## CSV and JSON

CSV files are written with Python's `csv.writer`, one row per valid offer per (metric, price) view, with frontier flags for each scope and the offer's latency (`latency_s`, `latency_display`, `table_latency_s`) and measured Arena cost (`arena_cost_per_task_usd`, `arena_cost_n`). A text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'` so spreadsheets do not run it as a formula; numbers are written unchanged. `offers.json` keeps every raw label and source string.

## Known limits

- Prices are list prices, not the cost of a task.
- Table values move within minutes; every Table capture keeps its own read time.
- Whether a visitor who is not logged in sees every Table column is not yet known: the 2026-10-07 fixtures were read in the admin's Chrome, and whether that session was logged in was not checked.
- Per-image prices need the typed endpoint answers; with the saved fixtures only `bytedance-seed/seedream-4.5` has one.
- The two model-page routes are not documented API; OpenRouter may change or rate-limit them without notice. Arena covers only part of each modality: of 13 image, video and speech models sampled on 2026-10-08, 7 had a score, 4 answered 404 and 2 had 0 checks run.
- Model-page latency covers the 30 minutes before the fetch; a model with no recent request has none.

## Development

```bash
python3 -m pytest                # offline; sockets are blocked in tests
python3 tests/fixture_build.py   # builds .ihav_space/ihav-openrouter-pareto/ here from the saved fixtures
```

`tests/fixtures/openrouter_2026-10-07/` holds the real public answers and Table captures of 2026-10-07 with their `SHA256SUMS`; `tests/fixtures/openrouter_2026-10-08/` holds real model-page answers (Arena and latency) of 2026-10-08 for 16 models (18 offers) of that catalog.

## License

MIT
