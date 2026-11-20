"""brief-006 slice 4: the agent engine in threads, the timeout path, the split tool, follow-up mode, the rep guard.
No model is called: the agent turn is replaced where one would run."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.api import agent_host, service, threads  # noqa: E402
from pharmagentics.api.app import app  # noqa: E402

needs_db = pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
SCOPE = {"intent": "weekly_brief", "brand_id": "BXA", "territory_id": "PACIFIC", "week_start": "2026-06-08",
         "question": "Generate the weekly brand-performance briefing."}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setattr(threads, "_purged", True)


def analyst() -> TestClient:
    c = TestClient(app)
    c.post("/auth/dev-login", data={"username": "dev-analyst"}, follow_redirects=False)
    return c


@needs_db
def test_the_agent_engine_needs_the_app_to_run_the_agent(monkeypatch):
    a = analyst()
    bid = a.post("/api/briefing/query", json=SCOPE).json()["brief_id"]
    monkeypatch.setattr(agent_host, "model", lambda: None)
    r = a.post(f"/api/briefing/{bid}/thread/ask", json={"question": "Split this by plan", "engine": "agent"})
    assert r.status_code == 409 and "not available" in r.json()["detail"]


@needs_db
def test_an_agent_timeout_is_shown_and_keeps_no_answer(monkeypatch):
    a = analyst()
    bid = a.post("/api/briefing/query", json=SCOPE).json()["brief_id"]
    monkeypatch.setattr(threads, "_agent_answer", lambda result, q, s: {
        "answer": "Didn't finish in time; nothing was guessed.", "error": "timeout", "seconds": 60.0,
        "claims": [], "evidence": [], "cited": [], "kind": "timeout", "engine": "agent"})
    r = a.post(f"/api/briefing/{bid}/thread/ask", json={"question": "Split this by plan", "engine": "agent"})
    assert r.status_code == 504 and "nothing was guessed" in r.json()["detail"]
    assert a.get(f"/api/briefing/{bid}/thread").json()["turns"] == []  # FR-010: no answer text stored


@needs_db
def test_split_change_is_governed_traced_and_flags_small_cells(monkeypatch):
    from pharmagentics.mcp_server.server import RunSession
    monkeypatch.setenv("PHARMAGENTICS_MCP_FOLLOW_UP", "1")
    s = RunSession()
    try:
        s.open_run("Week of 2026-06-08 in Pacific: split by channel")
        text = s.split_change("PACIFIC", "channel")
        assert re.search(r"\{c\d+\}", text) and not re.search(r"\d", re.sub(r"\{c\d+\}", "", text))  # tokens only
        assert "CASH" in text and "small cell: noisy" in s.reg.render(text)
        assert s.split_change("PACIFIC", "rep").startswith("Unknown split")
        assert "Story so far" not in s.check_supply("PACIFIC")  # follow-up mode: no story-so-far status
    finally:
        s.close()


@needs_db
def test_a_rep_question_never_gets_a_rep():
    from briefing_baseline import answer as brief
    from pharmagentics.tools.followup import answer
    env = brief("Week of 2026-08-24 in Southeast: Generate the weekly brand-performance briefing.")
    turn = answer({**env, "brand_id": "BXA", "territory_id": "SOUTHEAST", "week_start": "2026-08-24"},
                  "Which rep stopped calling on Southeast doctors?")
    assert turn["kind"] == "no_individual" and not turn["claims"]
