"""Forecast lane API: access by role, the two views, fixed engine, validation, and the three ready-made cases.

These run the scripted engine (no language model) on the repo's own data/agent_visible, so they need no network.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import forecast, service
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
    monkeypatch.setenv("FEAGENT_WRITER", "off")  # no model call in these tests; the writer has its own tests
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


def test_the_first_weeks_of_the_release_run_without_a_baseline_week():
    sign_in("dev-forecast-analyst")
    for week in ("2024-10-14", "2024-10-21"):  # the comparison week two weeks earlier has no forecast row
        res = CLIENT.post("/api/forecast/runs", json={"territory_id": "NATIONAL", "week_start": week})
        assert res.status_code == 200, res.text
        deltas = next(e for e in res.json()["report"]["evidence"] if e["name"] == "get_region_deltas")["payload"]
        assert all(r["baseline_actual"] is None and r["delta_vs_baseline"] is None for r in deltas["regions"])


@pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
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


# ---- the question-driven agent (fcst-001) ---------------------------------------------------------------------------

def _wait(run_id: str) -> dict:
    import time

    for _ in range(100):
        body = CLIENT.get(f"/api/forecast/runs/{run_id}").json()
        if body["job_status"] != "running":
            return body
        time.sleep(0.1)
    raise AssertionError("the investigation did not finish")


def test_a_question_is_read_into_a_scope_before_it_runs(monkeypatch):
    monkeypatch.setenv("FORECAST_AGENT_MODEL", "rules")
    sign_in("dev-forecast-analyst")
    card = CLIENT.post("/api/forecast/scope", json={"question": "Top 5 largest gaps in the last 3 months"}).json()
    assert card["intent"] == "screen" and card["territory"] == "NATIONAL" and card["engine"] == "rules"
    assert CLIENT.post("/api/forecast/scope", json={"question": "hi", "engine": "x"}).status_code == 422


def test_a_question_runs_in_the_background_and_leaders_see_no_trace(monkeypatch):
    monkeypatch.setenv("FORECAST_AGENT_MODEL", "rules")
    sign_in("dev-forecast-analyst")
    started = CLIENT.post("/api/forecast/ask", json={"question": "Week of 2026-08-24: How much of the miss does each driver explain?"}).json()
    assert started["kind"] == "question"
    done = _wait(started["forecast_run_id"])
    assert done["job_status"] == "done" and done["report"]["variance_trx"] == -1036
    assert done["report"]["decisions"] and done["report"]["comparisons"]
    assert CLIENT.post(f"/api/forecast/runs/{started['forecast_run_id']}/submit").json()["review_status"] == "pending_review"
    sign_in("dev-forecast-manager")
    lead = CLIENT.get(f"/api/forecast/runs/{started['forecast_run_id']}").json()
    assert lead["view"] == "leadership" and "progress" not in lead
    for hidden in ("decisions", "comparisons", "candidates", "screen", "sections_all"):
        assert hidden not in lead["report"]
    assert {s["id"] for s in lead["report"]["sections"]} <= {"summary", "miss", "where", "screen", "attribution", "unknowns", "checks", "assumptions"}
    assert CLIENT.post("/api/forecast/ask", json={"question": "Top 5 largest gaps"}).status_code == 403


def test_a_scope_edit_overrides_the_parsed_weeks(monkeypatch):
    monkeypatch.setenv("FORECAST_AGENT_MODEL", "rules")
    sign_in("dev-forecast-analyst")
    started = CLIENT.post("/api/forecast/ask", json={"question": "Why did we miss?", "territory_id": "PACIFIC",
                                                     "week_from": "2026-06-01", "week_to": "2026-06-29"}).json()
    report = _wait(started["forecast_run_id"])["report"]
    assert report["territory_id"] == "PACIFIC" and report["window_weeks"] == 5
    assert any(d["driver"] == "supply" for d in report["drivers"])


def test_follow_ups_rerun_explain_and_break_down(monkeypatch):
    import time

    monkeypatch.setenv("FORECAST_AGENT_MODEL", "rules")
    sign_in("dev-forecast-analyst")
    rid = CLIENT.post("/api/forecast/ask", json={"question": "Week of 2026-08-24: How much of the miss does each driver explain?"}).json()["forecast_run_id"]
    _wait(rid)
    for q in ("Drop South Central from the controls and rerun", "Why not supply?", "Show it week by week"):
        assert CLIENT.post(f"/api/forecast/runs/{rid}/followups", json={"question": q}).status_code == 200
    for _ in range(100):
        body = CLIENT.get(f"/api/forecast/runs/{rid}").json()
        if all(f["status"] != "running" for f in body["followups"]):
            break
        time.sleep(0.1)
    rerun, why, weekly = body["followups"]
    assert rerun["op"] == "rerun" and rerun["child_run_id"]
    child = CLIENT.get(f"/api/forecast/runs/{rerun['child_run_id']}").json()
    promo = next(d for d in child["report"]["drivers"] if d["driver"] == "promotion")
    assert promo["impact_trx"] == -204 and child["report"]["residual_trx"] == -145 and child["parent_run_id"] == rid
    assert why["op"] == "explain" and "supply" in why["answer"]
    assert weekly["op"] == "weekly" and "-1,036" in weekly["answer"]
    sign_in("dev-forecast-manager")
    assert CLIENT.post(f"/api/forecast/runs/{rid}/followups", json={"question": "Why?"}).status_code == 403


def test_the_driver_board_is_readable_by_both_forecast_roles():
    for user in ("dev-forecast-analyst", "dev-forecast-manager"):
        sign_in(user)
        body = CLIENT.get("/api/forecast/drivers").json()
        assert body["labels"] == "draft" and isinstance(body["systems"], dict)


def test_the_scope_card_says_who_read_it_and_the_confirmed_intent_is_used(monkeypatch):
    monkeypatch.setenv("FORECAST_AGENT_MODEL", "rules")
    sign_in("dev-forecast-analyst")
    card = CLIENT.post("/api/forecast/scope", json={"question": "Week of 2026-08-24: Where is the miss?"}).json()
    assert card["read_by"] == "rules" and card["investigator"] == "rules" and card["intent"] == "where"
    started = CLIENT.post("/api/forecast/ask", json={"question": "Week of 2026-08-24: Where is the miss?", "territory_id": "NATIONAL",
                                                     "week_from": "2026-08-24", "week_to": "2026-08-24", "intent": "attribution"}).json()
    report = _wait(started["forecast_run_id"])["report"]
    assert report["intent"] == "attribution" and report["scope_read_by"] == "confirmed"
    assert CLIENT.post("/api/forecast/ask", json={"question": "Week of 2026-08-24", "intent": "guess"}).status_code == 422
