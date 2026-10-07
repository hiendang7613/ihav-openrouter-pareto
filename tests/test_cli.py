"""Command line contract: one JSON object per command and stable exit codes."""

from __future__ import annotations

import json
import subprocess
import sys

from fixture_build import CORE, FIXTURES, TABLES, make_capture
from ihav_openrouter_pareto.cli import main


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    return code, json.loads(capsys.readouterr().out)


def test_init_ingest_build_and_errors(tmp_path, capsys):
    code, out = run(capsys, "init", "--project", tmp_path)
    assert code == 0 and len(out["created"]) == 4
    _, capture_id = make_capture(tmp_path, tables={})
    name, expected, url, read_at, _ = TABLES["speech"]
    code, out = run(capsys, "ingest", "--project", tmp_path, "--modality", "speech", "--file", FIXTURES / name, "--url", url,
                    "--expected-rows", expected, "--captured-at", read_at)
    assert code == 0 and out["complete"] and out["capture_id"] == capture_id
    code, out = run(capsys, "ingest", "--project", tmp_path, "--modality", "speech", "--file", FIXTURES / name, "--url", url, "--expected-rows", 24)
    assert code == 3 and not out["complete"]
    code, out = run(capsys, "build", "--project", tmp_path)
    assert code == 3 and out["latest"] is None
    code, out = run(capsys, "build", "--project", tmp_path / "elsewhere")
    assert code == 2 and out["error"]["code"] == "not_initialised"
    code, out = run(capsys, "diff", "--project", tmp_path, "2026-10-07", "nope")
    assert code == 2 and out["error"]["code"] == "unknown_capture"
    code, out = run(capsys, "ingest", "--project", tmp_path)
    assert code == 2 and out["error"]["code"] == "usage"


def test_entry_script_runs_in_isolated_mode():
    done = subprocess.run([sys.executable, "-I", str(CORE / "scripts/pareto.py"), "--help"], capture_output=True, text=True, check=True)
    assert "init,fetch,ingest,build,diff" in done.stdout
