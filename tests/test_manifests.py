from __future__ import annotations

import json
import re

from fixture_build import ROOT
from ihav_openrouter_pareto import __version__

PLUGIN = ROOT / "plugins/ihav-openrouter-pareto"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_host_manifests_share_name_version_and_license():
    claude = load(PLUGIN / ".claude-plugin/plugin.json")
    codex = load(PLUGIN / ".codex-plugin/plugin.json")
    assert claude["name"] == codex["name"] == "ihav-openrouter-pareto"
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8").split("[project]", 1)[1].split("\n[", 1)[0]
    assert claude["version"] == codex["version"] == __version__ == re.search(r'^version = "([^"]+)"', project, re.M).group(1)
    assert claude["license"] == codex["license"] == "MIT"
    assert claude["skills"] == "./claude/skills" and codex["skills"] == "./core/"
    assert "usage, not quality" in codex["interface"]["longDescription"]


def test_both_marketplaces_point_to_the_plugin_and_skill_paths_exist():
    claude_market = load(ROOT / ".claude-plugin/marketplace.json")
    codex_market = load(ROOT / ".agents/plugins/marketplace.json")
    assert claude_market["plugins"][0]["name"] == codex_market["plugins"][0]["name"] == "ihav-openrouter-pareto"
    assert claude_market["plugins"][0]["source"] == codex_market["plugins"][0]["source"]["path"] == "./plugins/ihav-openrouter-pareto"
    assert (PLUGIN / "claude/skills/ihav-openrouter-pareto/SKILL.md").is_file()
    assert (PLUGIN / "core/ihav-openrouter-pareto/SKILL.md").is_file()
    assert (PLUGIN / "core/ihav-openrouter-pareto/scripts/pareto.py").is_file()
    assert not (ROOT / "skills").exists()
