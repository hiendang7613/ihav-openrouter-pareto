Public, key-free GETs of 2026-10-08 11:49 Asia/Ho_Chi_Minh (no cookie, no login), for plan bản 3 (model-page data):
- `arena_<modality>_<permaslug>.json`: https://openrouter.ai/api/frontend/v1/arena/explore/models/<permaslug>?tab=<image|video|speech>
  ("Checks passed" is `data.standing.checksPassed / checksTotal`); 3 answered 404 "Model has no public Arena results on this tab".
- `stats_<modality>_<permaslug>.json`: https://openrouter.ai/api/frontend/v1/stats/endpoint?permaslug=<permaslug>&variant=standard&perfWorkload=<w>&latencyMetric=<m>
  (per provider: `stats.p50_latency` in ms over 30 minutes, and `display_pricing`, which carries the video per-second prices).
- `urls.json`: every URL asked, its HTTP status, file and read time.

Models: a few per modality of the 2026-10-07 catalog fixture (`../openrouter_2026-10-07/models_all.json`), matched by its `canonical_slug`:
image (gemini-3.1-flash-image-preview, also a text model; seedream-4.5; gpt-image-2.5-sunburst; ming-image-0.1-design, Arena 404; muse-image),
video (veo-3.1; kling-v3.0-pro; seedance-2.0, also per-M-token SKUs; flux-video-upscale, per megapixel-second, Arena 404; heygen avatar-iv, Arena 404),
speech (mai-voice-2; gemini-3.8-flash-tts; fish-audio s2.1-pro-free, Arena 404), text (claude-sonnet-5.5, which shares its permaslug with `:batch`),
decisions (liquid d1; respan span-01-lite, which shares its permaslug with `:free`). Every other model of the catalog answers 404 in the offline replay.
