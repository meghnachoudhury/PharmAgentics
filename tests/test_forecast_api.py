"""Forecast lane API: access by role, the two views, fixed engine, validation, and the three ready-made cases.

These run the scripted engine (no language model) on the repo's own data/agent_visible, so they need no network.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import forecast
from pharmagentics.api.app import app

CLIENT = TestClient(app)
NATIONAL = {"territory_id": "NATIONAL", "week_start": "2026-08-24"}
NEW_ENGLAND = {"territory_id": "NEW_ENGLAND", "week_start": "2026-05-04"}
MID_ATLANTIC = {"territory_id": "MID_ATLANTIC", "week_start": "2025-08-04", "window_weeks": 13}


@pytest.fixture(autouse=True)
def _dev_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("FEAGENT_MODE", raising=False)
    CLIENT.cookies.clear()


def sign_in(user: str) -> None:
    CLIENT.cookies.clear()
    assert CLIENT.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303


def test_runs_need_a_signed_in_forecast_role():
    assert CLIENT.post("/api/forecast/runs", json=NATIONAL).status_code == 401
    sign_in("dev-analyst")  # a Briefing role holds no Forecast role
    assert CLIENT.post("/api/forecast/runs", json=NATIONAL).status_code == 403
    assert CLIENT.get("/api/forecast/cases").status_code == 403


def test_the_analyst_gets_the_full_run():
    sign_in("dev-forecast-analyst")
    res = CLIENT.post("/api/forecast/runs", json=NATIONAL)
    assert res.status_code == 200
    body = res.json()
    assert body["view"] == "analyst" and body["lane"] == "forecast"
    assert len(body["stages"]) == 7 and body["stages"][6]["status"] == "PENDING"
    report = body["report"]
    assert report["variance_trx"] == -1036 and report["investigator_mode"] == "stub"
    promotion = next(d for d in report["drivers"] if d["driver"] == "promotion")
    assert abs(promotion["impact_trx"] + 211.8) < 0.1 and promotion["evidence_ids"]
    assert res.headers["cache-control"] == "no-store"


def test_the_leadership_view_has_no_evidence_or_trace():
    sign_in("dev-forecast-analyst")
    body = CLIENT.post("/api/forecast/runs", json={**NATIONAL, "view": "leadership"}).json()
    assert body["view"] == "leadership"
    assert "stages" not in body and "pin" not in body and "fingerprint" not in body
    report = body["report"]
    assert report["variance_trx"] == -1036 and report["verification"] == {"verdict": "WARN"}
    assert "evidence" not in report and "investigator_mode" not in report
    assert all(set(d) == {"driver", "impact_trx", "confidence"} for d in report["drivers"])
    assert "evidence_ids" not in str(body)


def test_the_brand_manager_cannot_start_a_run_or_list_the_cards():
    sign_in("dev-forecast-manager")
    assert CLIENT.post("/api/forecast/runs", json=NATIONAL).status_code == 403
    assert CLIENT.get("/api/forecast/cases").status_code == 403
    status = CLIENT.get("/api/forecast/status").json()
    assert status["persona"] == "BM" and status["views"] == ["leadership"] and status["actions"] == ["read", "review"]


def test_an_analyst_can_preview_the_leadership_view_but_a_manager_cannot_open_the_analyst_view():
    sign_in("dev-forecast-analyst")
    preview = CLIENT.post("/api/forecast/runs", json={**NATIONAL, "view": "leadership"}).json()
    assert preview["view"] == "leadership" and "stages" not in preview


def test_opening_a_saved_run_in_both_views_keeps_the_same_run_and_review_state():
    sign_in("dev-forecast-analyst")
    created = CLIENT.post("/api/forecast/runs", json=NATIONAL).json()
    run_id = created["forecast_run_id"]
    path = f"/api/forecast/runs/{run_id}"

    preview_response = CLIENT.get(path, params={"view": "leadership"})
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["view"] == "leadership" and preview["forecast_run_id"] == run_id
    assert preview["review_status"] == created["review_status"] == "not_submitted"
    assert preview["report"]["variance_trx"] == created["report"]["variance_trx"]
    assert "stages" not in preview and "history" not in preview and "pin" not in preview
    assert "evidence" not in preview["report"]
    assert all("evidence_ids" not in d for d in preview["report"]["drivers"])

    for params in ({"view": "analyst"}, {}):
        response = CLIENT.get(path, params=params)
        assert response.status_code == 200
        analyst = response.json()
        assert analyst["view"] == "analyst" and analyst["forecast_run_id"] == run_id
        assert analyst["review_status"] == "not_submitted" and len(analyst["stages"]) == 7


def test_a_provisional_actual_pauses_attribution():
    sign_in("dev-forecast-analyst")
    body = CLIENT.post("/api/forecast/runs", json=NEW_ENGLAND).json()
    assert body["report"]["abstained"] is True and body["report"]["drivers"] == []
    assert body["report"]["variance_trx"] == -173
    assert body["stages"][1]["status"] == "FLAG" and body["stages"][3]["status"] == "ABSTAINED"


def test_a_thirteen_week_window_explains_the_window_not_the_first_week():
    sign_in("dev-forecast-analyst")
    report = CLIENT.post("/api/forecast/runs", json=MID_ATLANTIC).json()["report"]
    assert report["window_weeks"] == 13 and report["variance_trx"] == -730


def test_bad_input_is_refused_with_a_message():
    sign_in("dev-forecast-analyst")
    assert CLIENT.post("/api/forecast/runs", json={**NATIONAL, "territory_id": "ATLANTIS"}).status_code == 422
    assert CLIENT.post("/api/forecast/runs", json={**NATIONAL, "window_weeks": 99}).status_code == 422
    assert CLIENT.post("/api/forecast/runs", json={**NATIONAL, "mode": "ollama"}).status_code == 422  # not the caller's choice
    res = CLIENT.post("/api/forecast/runs", json={**NATIONAL, "week_start": "1999-01-04"})
    assert res.status_code == 400 and res.json()["detail"]


def test_the_engine_is_fixed_by_the_server_and_an_unknown_setting_means_stub(monkeypatch):
    monkeypatch.setenv("FEAGENT_MODE", "not-a-mode")
    assert forecast.engine_mode() == "stub"
    monkeypatch.setenv("FEAGENT_MODE", "ollama")
    assert forecast.engine_mode() == "ollama"
    monkeypatch.delenv("FEAGENT_MODE")
    assert forecast.engine_mode() == "stub"
    sign_in("dev-forecast-analyst")
    assert CLIENT.get("/api/forecast/status").json()["engine"] == "stub"


def test_cases_list_the_three_ready_made_requests():
    sign_in("dev-forecast-analyst")
    cases = CLIENT.get("/api/forecast/cases").json()["cases"]
    assert [c["request"]["territory_id"] for c in cases] == ["NEW_ENGLAND", "NATIONAL", "MID_ATLANTIC"]
    assert cases[2]["request"]["window_weeks"] == 13
    for case in cases:
        assert CLIENT.post("/api/forecast/runs", json=case["request"]).status_code == 200


def test_context_exposes_the_governed_forecast_scope():
    sign_in("dev-forecast-analyst")
    body = CLIENT.get("/api/forecast/context").json()
    assert body["metric"] == "TRx" and "NATIONAL" in body["territory_ids"]
    assert body["latest_week"] in body["available_weeks"]
    sign_in("dev-forecast-manager")
    assert CLIENT.get("/api/forecast/context").status_code == 403


def test_the_lane_is_open_to_the_ui():
    sign_in("dev-forecast-analyst")
    status = CLIENT.get("/api/forecast/status").json()
    assert status["available"] is True and status["actions"] == ["run", "read"]
