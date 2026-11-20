"""brief-006 slice 3: threads of follow-ups (FR-008, FR-009, FR-012; ADR 0002). Dev identities, real scripted engine."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import service, store, threads
from pharmagentics.api.app import app

needs_db = pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
SCOPE = {"intent": "weekly_brief", "brand_id": "BXA", "territory_id": "PACIFIC", "week_start": "2026-06-08",
         "question": "Generate the weekly brand-performance briefing."}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setattr(threads, "_purged", True)


def signed_in(user: str) -> TestClient:
    c = TestClient(app)
    c.post("/auth/dev-login", data={"username": user}, follow_redirects=False)
    return c


@pytest.fixture
def brief_id():
    return signed_in("dev-analyst").post("/api/briefing/query", json=SCOPE).json()["brief_id"]


@needs_db
def test_ask_save_share_and_continue(brief_id):
    a, b = signed_in("dev-analyst"), signed_in("dev-tester")
    empty = a.get(f"/api/briefing/{brief_id}/thread").json()
    assert empty["turns"] == [] and empty["suggestions"]["3.1"]
    t = a.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "What did the checks find?", "section": "3.1"}).json()
    assert t["turns"][0]["cited"] == ["3.1"] and t["turns"][0]["engine"] == "scripted" and not t["saved"]
    assert b.get(f"/api/briefing/{brief_id}/thread").json()["turns"] == []  # one thread per analyst
    assert b.get(f"/api/briefing/{brief_id}/thread/shared/{t['owner']}").status_code == 404  # unsaved: not shared
    saved = a.post(f"/api/briefing/{brief_id}/thread/save").json()
    assert saved["saved"] and saved["share_path"].endswith(t["owner"])
    seen = b.get(saved["share_path"]).json()
    assert seen["mine"] is False and len(seen["turns"]) == 1
    mine = b.post(f"/api/briefing/{brief_id}/thread/continue/{t['owner']}").json()
    assert mine["mine"] and mine["shared_from"] == t["owner"] and len(mine["turns"]) == 1 and not mine["saved"]


@needs_db
def test_leaders_never_reach_a_thread(brief_id):
    a, d = signed_in("dev-analyst"), signed_in("dev-director")
    a.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "Restate the bottom line"})
    owner = a.post(f"/api/briefing/{brief_id}/thread/save").json()["owner"]
    for path in ("", "/shared/" + owner):
        assert d.get(f"/api/briefing/{brief_id}/thread{path}").status_code in (403, 404)
    assert d.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "x"}).status_code in (403, 404)


@needs_db
def test_a_thread_holds_twenty_follow_ups(brief_id, monkeypatch):
    monkeypatch.setattr(threads, "MAX_TURNS", 3)
    a = signed_in("dev-analyst")
    for _ in range(3):
        assert a.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "Restate the next checks", "section": "5"}).status_code == 200
    full = a.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "One more"})
    assert full.status_code == 409 and "full" in full.json()["detail"]


@needs_db
def test_unsaved_threads_go_after_thirty_days_saved_ones_stay(brief_id):
    a = signed_in("dev-analyst")
    a.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "Restate the bottom line"})
    later = datetime.now(timezone.utc) + timedelta(days=31)
    assert threads.purge(now=later) == 1
    a.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "Restate the bottom line"})
    a.post(f"/api/briefing/{brief_id}/thread/save")
    assert threads.purge(now=later) == 0


@needs_db
def test_a_vote_on_a_follow_up_records_that_turn(brief_id):
    a = signed_in("dev-analyst")
    a.post(f"/api/briefing/{brief_id}/thread/ask", json={"question": "Restate the next checks", "section": "5"})
    r = a.post("/api/feedback/vote", json={"lane": "briefing", "ref": f"{brief_id}:t1", "view": "analyst", "vote": "up"})
    assert r.status_code in (200, 201), r.text
    keys = store.backend().keys("")
    vote = next(k for k in keys if "/t1/" in k)
    assert json.loads(store.backend().read(vote))["vote"] == "up"
    assert a.post("/api/feedback/vote", json={"lane": "briefing", "ref": f"{brief_id}:t9", "view": "analyst",
                                              "vote": "up"}).status_code == 404
