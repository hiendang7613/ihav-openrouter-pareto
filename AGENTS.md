# ihav-openrouter-pareto: agent notes

- Plan (approved 2026-10-07 13:21, bản 2, SHA-256 `698866c5…`): `vulcan_repos/ai-image_tools/ai-image-studio/labs/plans/openrouter_pareto_plugin_plan.md` in the ai-ucg-design workspace, plus its bản 3 delta `openrouter_pareto_plan_v3_delta.md` beside it (approved 2026-10-08 11:42, SHA-256 `e76d39fd…`; approvals in `APPROVALS.md` there). Changes beyond them need a new approved plan.
- Layout: host manifests in `plugins/ihav-openrouter-pareto/.claude-plugin/` and `.codex-plugin/`; the Claude skill in `claude/skills/`; the shared core, Codex skill and entry script in `core/ihav-openrouter-pareto/`.
- The core is standard-library Python 3.9+, JSON in and out. The page script in `ihav_openrouter_pareto/assets/app.js` only selects precomputed views and draws them; frontiers are computed in Python.
- Tests: `python3 -m pytest` from the repository root. They never touch the network; the real 2026-10-07 answers live in `tests/fixtures/openrouter_2026-10-07/` and the 2026-10-08 model-page answers in `tests/fixtures/openrouter_2026-10-08/`, each with `SHA256SUMS`.
- `python3 tests/fixture_build.py [project]` builds the HTML, CSV and JSON from those fixtures offline.
- Never call a paid API, read `.env` files, or store keys or cookies. Only the public, key-free GETs in `fetch.py` are allowed, and only when fresh data is needed.
- `scripts/charts.py` is the one-command, no-LLM run (five tabs; `--offline` replays the fixtures). A live run on 2026-10-08 made 675 public GETs in 9 min 26 s, 613 of them to the two model-page routes (`arena/explore`, `stats/endpoint`).
