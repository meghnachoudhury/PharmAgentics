"""core-007 FR-028: agent jobs for the owner's local worker. The worker is simulated: its posted results
are built from the scripted engine, so these tests need no model."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.api import cloud, jobs, service  # noqa: E402
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
    for k in ("PHARMAGENTICS_CLOUD_AGENT_JOB", "PHARMAGENTICS_GCP_PROJECT", "PHARMAGENTICS_CLOUD_MAX_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    jobs.reset()
    cloud.reset()
    yield
    jobs.reset()
    cloud.reset()


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
    assert worker().post("/api/worker/next", json={"worker": "pc-1"}, headers=W).json()["id"] == a["id"]
    assert worker().post("/api/worker/next", json={"worker": "pc-1"}, headers=W).status_code == 204  # pc-1 still runs a
    assert worker().post("/api/worker/next", json={"worker": "pc-2"}, headers=W).json()["id"] == b["id"]  # a second host helps


def test_host_status_follows_the_polls():
    analyst = signed_in("dev-analyst")
    assert analyst.get("/api/agent/status").json()["online"] is False
    worker().post("/api/worker/next", json={"model": "ollama:qwen3"}, headers=W)
    status = analyst.get("/api/agent/status").json()
    assert status["online"] is True and status["model"] == "ollama:qwen3"
    assert [h["name"] for h in analyst.get("/api/agent/status").json()["hosts"]] == ["worker"]
    for h in jobs._hosts.values():
        h["last_seen"] -= 120
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


# --- core-007 FR-031: heartbeat, stale jobs, and the cloud CPU host ---------------------------------

def _running_job_on(worker_name: str):
    analyst = signed_in("dev-analyst")
    job = analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()
    assert worker().post("/api/worker/next", json={"worker": worker_name}, headers=W).json()["id"] == job["id"]
    return analyst, job["id"]


@pytest.mark.parametrize(("worker_name", "host_kind"), [("cloud", "cloud_cpu"), ("meghna-pc", "teammate")])
def test_job_view_reports_the_host_that_actually_took_the_job(worker_name, host_kind):
    analyst = signed_in("dev-analyst")
    submitted = analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q}).json()
    job_id = submitted["id"]
    assert submitted["status"] == "queued" and submitted["host_kind"] is None
    assert analyst.get(f"/api/agent/jobs/{job_id}").json()["host_kind"] is None

    worker().post("/api/worker/next", json={"worker": worker_name}, headers=W)
    running = analyst.get(f"/api/agent/jobs/{job_id}").json()
    assert running["status"] == "running" and running["host_kind"] == host_kind
    assert "worker" not in running  # expose the host class, not the machine's name

    worker().post(f"/api/worker/jobs/{job_id}", json={"ok": False, "error": "test"}, headers=W)
    failed = analyst.get(f"/api/agent/jobs/{job_id}").json()
    assert failed["status"] == "failed" and failed["host_kind"] == host_kind


def test_heartbeat_keeps_a_long_job_alive_and_silence_fails_it():
    analyst, job_id = _running_job_on("pc-1")
    jobs.get(job_id)["started_ts"] -= 1200  # twenty minutes in: a slow CPU run, not a stuck one
    assert worker().post("/api/worker/heartbeat", json={"worker": "pc-1"}, headers=W).status_code == 204
    assert analyst.get(f"/api/agent/jobs/{job_id}").json()["status"] == "running"
    jobs._BOOT -= 1000  # (the grace period after an app restart is over)
    jobs._hosts["pc-1"]["last_seen"] -= 400  # the worker went quiet
    failed = analyst.get(f"/api/agent/jobs/{job_id}").json()
    assert failed["status"] == "failed" and "stopped answering" in failed["error"]
    assert worker().post("/api/worker/heartbeat", json={"worker": "x"}).status_code == 401  # token required


def test_a_job_over_the_hard_cap_fails_even_with_a_heartbeat():
    analyst, job_id = _running_job_on("pc-1")
    jobs.get(job_id)["started_ts"] -= jobs.MAX_RUN_SECONDS + 5
    worker().post("/api/worker/heartbeat", json={"worker": "pc-1"}, headers=W)
    assert analyst.get(f"/api/agent/jobs/{job_id}").json()["status"] == "failed"


def _enable_cloud(monkeypatch, calls):
    monkeypatch.setenv("PHARMAGENTICS_CLOUD_AGENT_JOB", "pharmagentics-agent")
    monkeypatch.setenv("PHARMAGENTICS_GCP_PROJECT", "pharmagentics")
    monkeypatch.setattr(cloud, "_post", lambda url: calls.append(url))


def test_cloud_host_starts_only_when_work_waits_and_nobody_hosts(monkeypatch):
    calls: list[str] = []
    _enable_cloud(monkeypatch, calls)
    analyst = signed_in("dev-analyst")
    assert analyst.get("/api/agent/status").json()["cloud"]["enabled"] is True
    assert calls == []  # nothing is waiting
    analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q})
    assert calls == ["https://run.googleapis.com/v2/projects/pharmagentics/locations/us-central1/jobs/pharmagentics-agent:run"]
    analyst.get("/api/agent/status")
    assert len(calls) == 1  # one start, not one per poll (cooldown)
    assert analyst.get("/api/agent/status").json()["cloud"]["starting"] is True


def test_a_teammates_machine_goes_first(monkeypatch):
    calls: list[str] = []
    _enable_cloud(monkeypatch, calls)
    worker().post("/api/worker/next", json={"worker": "meghna-pc"}, headers=W)  # a host is online
    signed_in("dev-analyst").post("/api/agent/jobs", json={"kind": "triage", "query": Q})
    assert calls == []


def test_cloud_budget_stops_new_starts_and_counts_cloud_jobs(monkeypatch):
    calls: list[str] = []
    _enable_cloud(monkeypatch, calls)
    monkeypatch.setenv("PHARMAGENTICS_CLOUD_MAX_SECONDS", str(cloud.START_OVERHEAD + 50))
    analyst = signed_in("dev-analyst")
    analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q})
    assert len(calls) == 1 and cloud.seconds_left() == 50
    # the cloud host takes the job and finishes it: its running time is charged to the budget
    job = worker().post("/api/worker/next", json={"worker": "cloud"}, headers=W).json()
    jobs.get(job["id"])["started_ts"] -= 120
    worker().post(f"/api/worker/jobs/{job['id']}", json={"ok": False, "error": "test"}, headers=W)
    assert cloud.seconds_left() == 0 and cloud.usage()["job_seconds"] >= 120
    cloud.reset()
    jobs._hosts.clear()
    analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q})
    assert len(calls) == 1  # budget used up: no second start
    assert "budget" in analyst.get("/api/agent/status").json()["cloud"]["error"]


def test_a_failed_start_is_reported_and_refunded(monkeypatch):
    _enable_cloud(monkeypatch, [])
    monkeypatch.setattr(cloud, "_post", lambda url: (_ for _ in ()).throw(RuntimeError("HTTP 403")))
    analyst = signed_in("dev-analyst")
    analyst.post("/api/agent/jobs", json={"kind": "triage", "query": Q})
    st = analyst.get("/api/agent/status").json()["cloud"]
    assert "could not start" in st["error"] and cloud.usage()["starts"] == 0


def test_cloud_is_off_unless_configured():
    st = signed_in("dev-analyst").get("/api/agent/status").json()["cloud"]
    assert st["enabled"] is False
