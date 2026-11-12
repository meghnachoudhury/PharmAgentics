"""core-007 FR-028: agent jobs for the owner's local worker. The worker is simulated: its posted results
are built from the scripted engine, so these tests need no model."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.api import jobs, service  # noqa: E402
from pharmagentics.api.app import app  # noqa: E402

pytestmark = pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
TOKEN = "test-worker-token"
Q = {"intent": "weekly_brief", "brand_id": "BXA", "territory_id": "MID_ATLANTIC", "week_start": "2026-07-13",
     "question": "What changed, and why?"}
W = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PHARMAGENTICS_WORKER_TOKEN", TOKEN)
    monkeypatch.delenv("K_SERVICE", raising=False)
    jobs.reset()
    yield
    jobs.reset()


def signed_in(user: str) -> TestClient:
    c = TestClient(app)
    c.post("/auth/dev-login", data={"username": user})
    return c


def worker() -> TestClient:
    return TestClient(app)


def _plan():
    from briefing_baseline.pipeline import triage

    return triage(service.normalize_question(service.BriefingQuery.model_validate(Q)))


def _triage_done(analyst):
    job = analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()
    taken = worker().post("/api/worker/next", json={"model": "ollama:test"}, headers=W).json()
    assert taken["id"] == job["id"] and taken["kind"] == "triage"
    plan = dict(_plan(), engine="agent", manager_order=["territory:PACIFIC"], flagged=True, flags=["The manager changed code's plan."])
    assert worker().post(f"/api/worker/jobs/{job['id']}", json={"ok": True, "result": plan}, headers=W).json()["status"] == "done"
    return job["id"], plan


def test_worker_endpoints_need_the_token(monkeypatch):
    assert worker().post("/api/worker/next", json={}).status_code == 401
    assert worker().post("/api/worker/next", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    monkeypatch.delenv("PHARMAGENTICS_WORKER_TOKEN")
    assert worker().post("/api/worker/next", json={}, headers=W).status_code == 503


def test_only_analysts_submit_and_one_job_runs_at_a_time():
    assert signed_in("dev-director").post("/api/agent/jobs", json={"kind": "triage", "query": Q}).status_code == 403
    analyst = signed_in("dev-analyst")
    a = analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()
    b = analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()
    assert a["status"] == b["status"] == "queued"
    assert worker().post("/api/worker/next", json={}, headers=W).json()["id"] == a["id"]
    assert worker().post("/api/worker/next", json={}, headers=W).status_code == 204  # a is still running


def test_host_status_follows_the_polls():
    analyst = signed_in("dev-analyst")
    assert analyst.get("/api/agent/status").json()["online"] is False
    worker().post("/api/worker/next", json={"model": "ollama:qwen3"}, headers=W)
    status = analyst.get("/api/agent/status").json()
    assert status["online"] is True and status["model"] == "ollama:qwen3"
    jobs._host["last_seen"] -= 120
    assert analyst.get("/api/agent/status").json()["online"] is False


def test_triage_then_brief_round_trip_and_traceability_check():
    from briefing_baseline.pipeline import run_with_plan

    analyst = signed_in("dev-analyst")
    plan_job, plan = _triage_done(analyst)
    shown = analyst.get(f"/api/agent/jobs/{plan_job}").json()
    assert shown["status"] == "done" and shown["result"]["flagged"] is True

    stale = {"kind": "brief", "query": Q, "triage_job": plan_job, "decision": {"plan_id": "t-000000000000", "stories": []}}
    assert analyst.post("/api/agent/jobs", json=stale).status_code == 409
    decision = {"plan_id": plan["plan_id"], "stories": ["territory:PACIFIC", "competitor:BXE"]}
    job = analyst.post("/api/agent/jobs", json={"kind": "brief", "query": Q, "triage_job": plan_job, "decision": decision}).json()
    taken = worker().post("/api/worker/next", json={}, headers=W).json()
    assert taken["payload"]["plan"]["plan_id"] == plan["plan_id"] and taken["payload"]["decision"] == decision

    good = run_with_plan(taken["payload"]["question"], decision)
    good["envelope"]["system"] = "briefing_agent:ollama:test"
    bad = {**good, "envelope": {**good["envelope"], "answer": good["envelope"]["answer"] + "\nPacific fell 99.9%."}}
    worker().post(f"/api/worker/jobs/{job['id']}", json={"ok": True, "result": bad}, headers=W)
    failed = analyst.get(f"/api/agent/jobs/{job['id']}").json()
    assert failed["status"] == "failed" and "99.9%" in failed["error"]

    job2 = analyst.post("/api/agent/jobs", json={"kind": "brief", "query": Q, "triage_job": plan_job, "decision": decision}).json()
    worker().post("/api/worker/next", json={}, headers=W)
    assert worker().post(f"/api/worker/jobs/{job2['id']}", json={"ok": True, "result": good}, headers=W).json()["status"] == "done"
    brief = analyst.get(f"/api/agent/jobs/{job2['id']}").json()["result"]
    assert brief["engine"] == "agent" and brief["system"] == "briefing_agent:ollama:test" and brief["flow"]
    assert brief["review_status"] == "pending"


def test_untraced_numbers_ignore_dates_versions_and_plan_ids():
    text = "Brief for week of 2026-07-13. Data version 06bcba77fbe1. Plan SYN_MID_ATLANTIC_MEDICARE_PART_D_1 fell 22.5%."
    assert service.untraced_numbers(text, [{"value": "22.5%"}], "06bcba77fbe1") == []
    assert service.untraced_numbers(text, [], "06bcba77fbe1") == ["22.5%"]
