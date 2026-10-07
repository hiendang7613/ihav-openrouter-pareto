# ihav-openrouter-pareto: agent notes

- Plan (approved 2026-10-07 13:21, bản 2, SHA-256 `698866c5…`): `ai-image_tools/ai-image-studio/labs/plans/openrouter_pareto_plugin_plan.md` in the ai-ucg-design workspace. Changes beyond it need a new approved plan.
- Layout: host manifests in `plugins/ihav-openrouter-pareto/.claude-plugin/` and `.codex-plugin/`; the Claude skill in `claude/skills/`; the shared core, Codex skill and entry script in `core/ihav-openrouter-pareto/`.
- The core is standard-library Python 3.9+, JSON in and out. The page script in `ihav_openrouter_pareto/assets/app.js` only selects precomputed views and draws them; frontiers are computed in Python.
- Tests: `python3 -m pytest` from the repository root. They never touch the network; the real 2026-10-07 answers live in `tests/fixtures/openrouter_2026-10-07/` with `SHA256SUMS`.
- `python3 tests/fixture_build.py [project]` builds the HTML, CSV and JSON from those fixtures offline.
- Never call a paid API, read `.env` files, or store keys or cookies. Only the public, key-free GETs in `fetch.py` are allowed, and only when fresh data is needed.
