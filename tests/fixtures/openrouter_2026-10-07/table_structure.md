# OpenRouter models page, Table view — structure observed 2026-10-07 13:49 (the admin's Chrome; session state not checked)

- One `<table>`; `thead th` (21): Model Name, Weekly Tokens, Input, Output, Context, Latency, Throughput, Intelligence,
  Coding, Agentic, DA ELO, Code Categories, UI Component, Game Development, Data Visualization, 3D, Image, Video, SVG,
  Released, (empty).
- `tbody tr` count = the count shown in the modality tab (Image 59): the table is complete, no pagination.
- The model link in a row is the `<a>` whose path has two segments (`/openai/gpt-image-2.5-sunburst`); the first link in
  the row is the provider page (one segment). The slug equals the API `id` without a variant suffix.
- A model with one price renders ONE `td` with `colspan=2` over Input/Output ("from $0.04", "$0.03"); parse by colspan,
  not by position. Price labels seen: "$8", "$0.50", "from $0.04", "$0" (free), "—".
- A discount is appended to the name cell text ("Black Forest Labs: FLUX.3 Image 50% off").
- Missing values are "—". Latency: "29.0s", "1m 4s", "2m 14s"; Weekly Tokens: "4.03B", "922M", "77.6M".
- Captures (2026-10-07, the admin's Chrome, read-only, Q3.a): the image (59 rows) and speech (23 rows) tables with every
  column, through the page console (`ORCAP|<modality>|<index>|...` log lines read back with a pattern filter); and the
  unfiltered table, all 651 rows, with only the three columns the API lacks (`openrouter_table_all_rows.txt`:
  index|slug|Weekly Tokens|Latency|Throughput, mapped by header and colspan in the page). No file download was needed.
- Verification: the all-rows file's SHA-256 equals the SHA-256 the page computed over the same lines
  (b9510e9c728a2e4412e8348ababa94b1fca73d17c665543b0932c57cb62493d5); its 651 slugs equal the 651 ids of
  `models_all.json` one to one (77 `:batch` rows, 19 `~...-latest` aliases, routers such as `openrouter/auto`).
- The unfiltered table holds every modality (text, image, video, speech, embeddings, audio), so the modality comes from
  the API join, not from the table.
- `order=top-weekly` is the page's own rank, not a sort of the Weekly Tokens column: transcription rows with "—" sit
  among text rows (index 254 `openai/whisper-large-v3-turbo`), and `google/gemini-3.5-transcribe` (178M) sits at 452
  below 83.3M. Keep the rank and the Weekly Tokens value as two fields.
- Values move within minutes: the same model read 4.03B and then 4.04B, latency 17.6s and then 18.1s. Every capture
  needs its own timestamp.
