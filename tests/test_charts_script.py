"""scripts/charts.py: one command, no browser, five tabs; the offline mode replays the saved fixtures."""

from __future__ import annotations

import importlib.util
import json

from fixture_build import ROOT

spec = importlib.util.spec_from_file_location("charts", ROOT / "scripts/charts.py")
charts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(charts)


def test_offline_run_builds_five_tabs_and_keeps_set_config(tmp_path, capsys):
    space = charts.Space(tmp_path)
    space.init()
    config = json.loads(space.config_path.read_text(encoding="utf-8"))
    config["price_components"]["speech"] = ["input"]
    space.config_path.write_text(json.dumps(config), encoding="utf-8")
    code = charts.main(["--offline", "--project", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["validated"] and out["mode"] == "offline"
    assert list(out["tabs"]) == ["text", "image", "video", "speech", "decisions"]
    assert out["tabs"]["decisions"]["valid"] == 13 and out["tabs"]["decisions"]["excluded"] == {"alias": 1}
    assert out["tabs"]["video"] == {"metric": None, "price": None, "valid": 0, "total": 30, "excluded": {}, "frontier": [], "unavailable": []}
    assert out["tabs"]["speech"]["price"] == "input|per_m_tokens" and "bytedance-seed/seedream-4.5" not in out["endpoints_failed"]
    config = json.loads(space.config_path.read_text(encoding="utf-8"))
    assert config["price_components"]["speech"] == ["input"] and config["price_components"]["video"] == []
    assert config["price_components"]["decisions"] == ["input", "output"]
    assert config["table_urls"]["decisions"].endswith("output_modalities=decisions")


def test_failed_fetch_is_one_json_error(tmp_path, capsys, monkeypatch):
    def offline(_space):
        raise charts.ParetoError("network error for https://openrouter.ai/api/v1/models", "network_error", 4)

    monkeypatch.setattr(charts, "fetch", offline)
    code = charts.main(["--project", str(tmp_path), "--modalities", "text,decisions"])
    out = json.loads(capsys.readouterr().out)
    assert code == 4 and out["error"]["code"] == "network_error"
    assert json.loads(charts.Space(tmp_path).config_path.read_text(encoding="utf-8"))["modalities"] == ["text", "decisions"]
