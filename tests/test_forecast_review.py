"""Forecast review flow: the Commercial Analytics Analyst runs and submits; the Brand Manager approves, rejects or
returns. Nothing is approved by the system, and the Brand Manager never runs the agent."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api.app import app

CLIENT = TestClient(app)
NATIONAL = {"territory_id": "NATIONAL", "week_start": "2026-08-24"}
NEW_ENGLAND = {"territory_id": "NEW_ENGLAND", "week_start": "2026-05-04"}


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("PHARMAGENTICS_STATE_BUCKET", raising=False)
    monkeypatch.delenv("FEAGENT_MODE", raising=False)
    CLIENT.cookies.clear()


def sign_in(user: str) -> None:
    CLIENT.cookies.clear()
    assert CLIENT.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303


def run(body=NATIONAL) -> str:
    sign_in("dev-forecast-analyst")
    res = CLIENT.post("/api/forecast/runs", json=body)
    assert res.status_code == 200
    return res.json()["forecast_run_id"]


def submitted(body=NATIONAL) -> str:
    rid = run(body)
    assert CLIENT.post(f"/api/forecast/runs/{rid}/submit").status_code == 200
    return rid


def decide(rid: str, decision: str, note: str | None = None):
    sign_in("dev-forecast-manager")
    return CLIENT.post(f"/api/forecast/runs/{rid}/review", json={"decision": decision, "note": note})


def test_a_new_run_is_never_approved_and_is_hidden_from_the_brand_manager():
    rid = run()
    body = CLIENT.get(f"/api/forecast/runs/{rid}").json()
    assert body["review_status"] == "not_submitted" and body["view"] == "analyst" and "stages" in body
    sign_in("dev-forecast-manager")
    assert CLIENT.get(f"/api/forecast/runs/{rid}").status_code == 404
    assert CLIENT.get("/api/forecast/runs").json()["runs"] == []


def test_the_brand_manager_cannot_run_or_submit():
    rid = run()
    sign_in("dev-forecast-manager")
    assert CLIENT.post("/api/forecast/runs", json=NATIONAL).status_code == 403
    assert CLIENT.post(f"/api/forecast/runs/{rid}/submit").status_code == 403


def test_a_submitted_run_reaches_the_brand_manager_as_an_executive_summary_only():
    rid = submitted()
    sign_in("dev-forecast-manager")
    rows = CLIENT.get("/api/forecast/runs", params={"status": "pending_review"}).json()["runs"]
    assert [r["forecast_run_id"] for r in rows] == [rid] and rows[0]["variance_trx"] == -1036
    body = CLIENT.get(f"/api/forecast/runs/{rid}").json()
    assert body["view"] == "leadership" and body["review_status"] == "pending_review"
    assert "stages" not in body and "evidence_ids" not in json.dumps(body) and "history" not in body
    assert CLIENT.get(f"/api/forecast/runs/{rid}", params={"view": "analyst"}).status_code == 403


def test_approving_records_the_decision_and_the_analyst_sees_it():
    rid = submitted()
    res = decide(rid, "approved")
    assert res.status_code == 200 and res.json()["review_status"] == "approved" and res.json()["reviewed_at"]
    sign_in("dev-forecast-analyst")
    body = CLIENT.get(f"/api/forecast/runs/{rid}").json()
    assert body["review_status"] == "approved"
    assert [h["action"] for h in body["history"]] == ["submitted", "approved"]
    assert [h["role"] for h in body["history"]] == ["forecast-analyst", "forecast-manager"]
    assert all(h["by"].startswith("u-") for h in body["history"])  # a pseudonym, never a name


def test_rejecting_or_returning_needs_a_note():
    rid = submitted()
    assert decide(rid, "rejected").status_code == 422
    assert decide(rid, "returned").status_code == 422
    assert decide(rid, "rejected", "Residual too large to act on").json()["review_note"] == "Residual too large to act on"


def test_a_returned_run_can_be_resubmitted_and_a_decided_run_cannot_be_decided_again():
    rid = submitted()
    assert decide(rid, "returned", "Check the promotion dates").json()["review_status"] == "returned"
    sign_in("dev-forecast-analyst")
    assert CLIENT.post(f"/api/forecast/runs/{rid}/submit").json()["review_status"] == "pending_review"
    assert decide(rid, "approved").status_code == 200
    assert decide(rid, "rejected", "changed my mind").status_code == 409
    sign_in("dev-forecast-analyst")
    assert CLIENT.post(f"/api/forecast/runs/{rid}/submit").status_code == 409


def test_a_run_that_was_never_submitted_cannot_be_reviewed():
    rid = run()
    assert decide(rid, "approved").status_code == 409


def test_the_analyst_cannot_review():
    rid = submitted()
    sign_in("dev-forecast-analyst")
    assert CLIENT.post(f"/api/forecast/runs/{rid}/review", json={"decision": "approved"}).status_code == 403


def test_a_rerun_of_the_same_request_keeps_its_review():
    rid = submitted()
    decide(rid, "approved")
    sign_in("dev-forecast-analyst")
    again = CLIENT.post("/api/forecast/runs", json=NATIONAL).json()
    assert again["forecast_run_id"] == rid and again["review_status"] == "approved"
    other = CLIENT.post("/api/forecast/runs", json=NEW_ENGLAND).json()
    assert other["forecast_run_id"] != rid and other["review_status"] == "not_submitted"


def test_unknown_or_malformed_ids_are_not_found():
    sign_in("dev-forecast-analyst")
    assert CLIENT.get("/api/forecast/runs/f-000000000000").status_code == 404
    assert CLIENT.get("/api/forecast/runs/../../etc/passwd").status_code in (404, 422)
    assert CLIENT.post("/api/forecast/runs/not-an-id/submit").status_code == 404


def test_a_briefing_role_has_no_access_to_forecast_runs():
    rid = run()
    sign_in("dev-analyst")
    assert CLIENT.get("/api/forecast/runs").status_code == 403
    assert CLIENT.get(f"/api/forecast/runs/{rid}").status_code == 403
