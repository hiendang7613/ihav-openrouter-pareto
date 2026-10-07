from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from fixture_build import ROOT

PLUGIN = ROOT / "plugins/ihav-openrouter-pareto"
CLAUDE = PLUGIN / "claude/skills/ihav-openrouter-pareto/SKILL.md"
CODEX = PLUGIN / "core/ihav-openrouter-pareto/SKILL.md"
REFERENCE = PLUGIN / "core/ihav-openrouter-pareto/references/table-capture.md"


def frontmatter(text):
    return dict(line.split(": ", 1) for line in text.split("---")[1].strip().splitlines())


def test_one_entry_skill_with_the_same_subcommands_and_rules_on_both_hosts():
    claude, codex = CLAUDE.read_text(encoding="utf-8"), CODEX.read_text(encoding="utf-8")
    assert frontmatter(claude)["name"] == frontmatter(codex)["name"] == "ihav-openrouter-pareto"
    assert frontmatter(claude)["argument-hint"] == "run | capture | build [capture_id] | diff <capture_a> <capture_b>"
    assert "scripts/pareto.py *" in frontmatter(claude)["allowed-tools"]
    for phrase in ("`run`", "`capture`", "`build [capture_id]`", "`diff <a> <b>`", "Never guess a price, score, unit or model match",
                   '`"validated": true`', "usage, not quality", "lower bound", "Table step skipped: no browser tool",
                   "`unavailable`", "HTTP 401, 403, 429", "No API key, cookie, login or paid call", "py -3", "not_comparable"):
        assert phrase in claude and phrase in codex, phrase


def test_skill_reference_links_resolve():
    assert (CLAUDE.parent / "../../../core/ihav-openrouter-pareto/references/table-capture.md").resolve() == REFERENCE.resolve()
    assert REFERENCE.is_file()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_table_capture_script_parses(tmp_path):
    script = re.search(r"```js\n(.*?)```", REFERENCE.read_text(encoding="utf-8"), re.S).group(1)
    (tmp_path / "capture.js").write_text(script, encoding="utf-8")
    subprocess.run(["node", "--check", str(tmp_path / "capture.js")], check=True)
