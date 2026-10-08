# ihav-openrouter-pareto

OpenRouter models as quality or weekly usage versus list price, with a Pareto frontier, inside Claude Code and Codex.

One build gives one self-contained HTML page (no CDN, no outbound request) with a tab per output modality (text, image, speech), plus a CSV per modality and one JSON file, all from the same observations and frontiers.

Status: 0.1.0, unreleased. Plan approved 2026-10-07 13:21 (ai-image_tools/ai-image-studio/labs/plans/openrouter_pareto_plugin_plan.md, bản 2, SHA-256 `698866c5…`). Not yet published to the ihav catalog.

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
| `diff <a> <b>` | price and metric changes, new and removed offers between two captures |

The skill owns the browser step: it opens `https://openrouter.ai/models?order=top-weekly&output_modalities=<m>`, switches to the Table view, reads the rows and hands the text to `ingest` ([contract](plugins/ihav-openrouter-pareto/core/ihav-openrouter-pareto/references/table-capture.md)). Without a browser tool, `build` still runs from the API alone and marks Weekly Tokens, Latency and Throughput `unavailable`.

The same commands work from a terminal; each prints one JSON object:

```bash
CLI=plugins/ihav-openrouter-pareto/core/ihav-openrouter-pareto/scripts/pareto.py
python3 $CLI init --project .
python3 $CLI fetch --project .
python3 $CLI ingest --project . --modality image --file table_image.txt \
  --url "https://openrouter.ai/models?order=top-weekly&output_modalities=image" --expected-rows 59
python3 $CLI build --project .
python3 $CLI diff --project . 20261007T053600Z 20261008T020000Z
```

Exit codes: `0` success, `2` usage or missing state, `3` incomplete Table or build not validated, `4` network or HTTP failure, `1` other errors.

One command without an LLM or a browser, from a checkout (tabs: text, image, video, speech, decisions; `--modalities` changes them):

```bash
python3 scripts/charts.py             # live: init, enable the tabs in config.json, fetch, build
python3 scripts/charts.py --offline   # no network: the saved 2026-10-07 answers and Table captures
```

A live run has no Table, so Weekly Tokens, Latency and Throughput are `unavailable`; the video and decisions tabs have no API metric and show "no chart". With the 2026-10-07 Tables, decisions charts weekly usage; video still has none, because its Weekly Tokens are `—` and its catalog prices are `0`.

## What the page shows

- A tab per modality in `config.json` (default text, image, speech).
- A selector of one metric, one price component with its unit, and one offer scope (`all`, `standard`, `batch`, `free`). Every part of the view follows that one selection: points, axes, the "n valid / N total" count, the reasons for exclusion, the frontier, hover and the table.
- Default views: text uses the Artificial Analysis Intelligence Index; image and speech use "Weekly usage vs price". The default price is the component and unit with the most valid offers for that metric.
- The x axis is a log scale of positive prices; price 0 sits in its own band on the left. The step line is the best score observed at a price up to that point; it does not stand for an intermediate model.
- Symbols: a circle is an exact price, a diamond a "from" price (a lower bound), a square a free offer, a hollow mark a 0 price inside a paid offer. Colours mark standard, batch and `:free` offers.

## Data rules

- **Sources.** Only OpenRouter. The public catalog (`/api/v1/models?output_modalities=all`) gives ids, names, prices and benchmarks; `/api/v1/images/models/<id>/endpoints` gives typed per-image or per-megapixel prices; the models Table gives Weekly Tokens, Latency, Throughput and the displayed price labels. `config.json` and each capture manifest record which field comes from which source.
- **Identity.** An offer is the verbatim API id, so `:batch` and `:free` offers stay separate. A Table row joins by its model link (the exact id), else by a unique full display name; otherwise it stays `unmatched` and gets no API price.
- **Prices.** Every price is kept as an observation: column, raw label, exact Decimal value, unit, component, qualifier (`exact`, `from`, `discounted`), discount, source and capture id. Catalog prices are USD per token and are shown per 1M tokens (an exact decimal shift). `-1` is a router sentinel, never a price. `0` is a valid price. Values are compared exactly; rounding happens only on display.
- **Table price units.** The Table text carries no unit. A label takes the unit of the one API or endpoint price of the same offer with an equal value; otherwise its unit is `unknown` and it is not plotted. A displayed discount is recorded and never applied again.
- **One price per chart.** A chart uses one component and one unit. Units are never converted. For one offer, a Table label confirmed this way is preferred, then a typed endpoint price, then the catalog price.
- **Metrics.** `aa.intelligence_index`, `aa.coding_index`, `aa.agentic_index`, `da.<arena>/<category>.elo` (one identity per arena and category; ELO is never merged across categories), `usage.weekly_tokens`, `perf.throughput_tps` and `perf.latency_s`. A missing score is not plotted and never counts as 0. Weekly tokens measure usage, not quality. Latency is shown in hover and the table, not as a chart axis, because lower is better and the frontier rule maximises the score.
- **Exclusions.** Routers by exact id (the seven `-1` rows of 2026-10-07, listed in `config.json`), any other `-1` row, and `~…-latest` aliases (shown as aliases of their target). `relace/relace-apply-3` and `relace/relace-search` are models and stay. Raw rows always stay in the capture.
- **Long-context tiers** (`pricing.overrides`) stay in the raw capture; charts use the base price.
- **Speech units.** The catalog reports speech prices in its per-token fields; the page shows the unit the API states. A provider may bill characters or seconds instead.

## State

```
./.ihav_space/ihav-openrouter-pareto/
  README.md  config.json
  captures/<capture_id>/   manifest.json, api_all.json, endpoints_<id>.json, table_<modality>.txt
  builds/<capture_id>/     offers.json, <modality>.csv, pareto.html
  latest -> builds/<capture_id>   moved only after a validated build (a one-line text file where symlinks are not allowed)
  history.jsonl            one line per capture, offer, metric and price basis; rebuilding adds no duplicate
```

A capture id is the UTC second of the fetch (`20261007T053600Z`); a second capture in the same second gets `-2`. `diff` and `build` also accept a date when exactly one capture has it. A build validates only when every ingested Table has all expected rows and parses, no Table file changed after ingest, and the page, CSV and JSON carry the same report.

## CSV and JSON

CSV files are written with Python's `csv.writer`, one row per valid offer per (metric, price) view, with frontier flags for each scope. A text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'` so spreadsheets do not run it as a formula; numbers are written unchanged. `offers.json` keeps every raw label and source string.

## Known limits

- Prices are list prices, not the cost of a task.
- Table values move within minutes; every Table capture keeps its own read time.
- Whether a visitor who is not logged in sees every Table column is not yet known: the 2026-10-07 fixtures were read in the admin's Chrome, and whether that session was logged in was not checked.
- Per-image prices need the typed endpoint answers; with the saved fixtures only `bytedance-seed/seedream-4.5` has one.

## Development

```bash
python3 -m pytest                # offline; sockets are blocked in tests
python3 tests/fixture_build.py   # builds .ihav_space/ihav-openrouter-pareto/ here from the saved fixtures
```

`tests/fixtures/openrouter_2026-10-07/` holds the real public answers and Table captures of 2026-10-07 with their `SHA256SUMS`.

## License

MIT
