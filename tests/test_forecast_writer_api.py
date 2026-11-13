"""The report writer inside the Forecast API: stored with the run, shaped per view, never changing the numbers.
The model calls are replaced; nothing here reaches a network."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from feagent import writer
from pharmagentics.api import forecast
from pharmagentics.api.app import app

CLIENT = TestClient(app)
NATIONAL = {"territory_id": "NATIONAL", "week_start": "2026-08-24"}
NEW_ENGLAND = {"territory_id": "NEW_ENGLAND", "week_start": "2026-05-04"}


@pytest.fixture(autouse=True)
def _state(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("PHARMAGENTICS_STATE_BUCKET", raising=False)
    monkeypatch.delenv("FEAGENT_MODE", raising=False)
    monkeypatch.delenv("FEAGENT_WRITER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    CLIENT.cookies.clear()


def sign_in(user: str) -> None:
    CLIENT.cookies.clear()
    assert CLIENT.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303


def prose(report):
    facts = writer.build_facts(report)
    return json.dumps({
        "summary": f"BXA Cardiovela missed its forecast by {abs(facts['variance_trx']):,} TRx.",
        "miss": f"Actual was {facts['actual_trx']:,} against a forecast of {facts['forecast_trx']:,}.",
        "residual": f"About {facts['residual_share_of_miss_pct']}% of the miss is unexplained.",
        "confidence": "These are associations against comparison regions, not proof of cause.",
        "next_checks": [{"check": "Confirm the event dates", "why": "The event date drives the estimate",
                         "owner": facts["what_to_check"][0]["owner"]}],
        "analyst_notes": "The event calendar is observable-only.",
    })


class Fake:
    """Stands in for the writer: Terra succeeds or fails, Qwen succeeds or fails, and every call is counted."""

    def __init__(self, terra="ok", local="fail"):
        self.terra, self.local, self.calls = terra, local, 0

    def __call__(self, report):
        self.calls += 1

        def make(mode):
            def call(messages, cfg):
                if mode == "fail":
                    raise writer.WriterError("http_500")
                return prose(report)
            return call

        return writer.write_report(report, terra=make(self.terra), local=make(self.local))


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")


def start(body=NATIONAL, user="dev-forecast-analyst"):
    """The POST response itself: what the caller gets before any model has written."""
    sign_in(user)
    res = CLIENT.post("/api/forecast/runs", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def run(body=NATIONAL, user="dev-forecast-analyst"):
    """The run once the writer has finished (the test client runs the background task before it returns)."""
    first = start(body, user)
    return CLIENT.get(f"/api/forecast/runs/{first['forecast_run_id']}").json()


def test_the_run_comes_back_at_once_and_the_prose_arrives_afterwards(monkeypatch, key):
    monkeypatch.setattr(forecast, "_write", Fake(terra="ok"))
    first = start()
    assert first["writer_status"] == "pending" and first["narrative"] is None and first["report_model"] == "none"
    assert first["report"]["variance_trx"] == -1036 and len(first["stages"]) == 7  # the answer does not wait
    later = CLIENT.get(f"/api/forecast/runs/{first['forecast_run_id']}").json()
    assert later["writer_status"] == "ok" and later["narrative"]["summary"]
    assert numbers(later) == numbers(first)


def test_a_review_made_while_the_prose_is_being_written_is_kept(monkeypatch, key):
    from pharmagentics.api import forecast_store
    monkeypatch.setattr(forecast, "_write_and_store", lambda run_id, report: None)  # the writer has not finished yet
    rid = start()["forecast_run_id"]
    assert CLIENT.post(f"/api/forecast/runs/{rid}/submit").json()["writer_status"] == "pending"
    forecast_store.set_writer(rid, Fake(terra="ok")(forecast_store.get(rid)["result"]["report"]))
    body = CLIENT.get(f"/api/forecast/runs/{rid}").json()
    assert body["review_status"] == "pending_review" and body["writer_status"] == "ok"


def test_a_run_still_being_written_is_not_started_twice_but_a_lost_one_is(monkeypatch, key):
    from pharmagentics.api import forecast_store
    calls = []
    monkeypatch.setattr(forecast, "_write_and_store", lambda run_id, report: calls.append(run_id))
    rid = start()["forecast_run_id"]
    start()
    assert calls == [rid]  # the second request found it pending and left it alone
    record = forecast_store.get(rid)
    record["writer_started_at"] = "2020-01-01T00:00:00.000+00:00"  # lost in a restart long ago
    forecast_store._put(record)
    start()
    assert calls == [rid, rid]


def test_a_new_run_carries_the_prose_and_which_model_wrote_it(monkeypatch, key):
    monkeypatch.setattr(forecast, "_write", Fake(terra="ok"))
    body = run()
    assert body["writer_status"] == "ok" and body["report_model"] == "gpt-6.1-terra"
    assert body["narrative"]["summary"] and body["narrative"]["analyst_notes"]
    assert body["writer_attempts"] == [{"model": "gpt-6.1-terra", "outcome": "ok"}]


def numbers(body):
    """Everything the scripted engine decides: the amounts, the drivers, the confidence and the verdict."""
    r = body["report"]
    return (r["forecast_trx"], r["actual_trx"], r["variance_trx"], r["residual_trx"], r["abstained"],
            [(d["driver"], d["impact_trx"], d["confidence"]) for d in r["drivers"]], r["verification"]["verdict"],
            [s["status"] for s in body["stages"]])


def test_the_scripted_numbers_are_the_same_with_the_writer_working_failing_or_off(monkeypatch, key, tmp_path):
    monkeypatch.setattr(forecast, "_write", Fake(terra="ok"))
    working = run()
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path / "failing"))
    monkeypatch.setattr(forecast, "_write", Fake(terra="fail", local="fail"))
    failing = run()
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path / "off"))
    monkeypatch.setenv("FEAGENT_WRITER", "off")
    off = run()
    assert (working["writer_status"], failing["writer_status"], off["writer_status"]) == ("ok", "fallback_stub", "skipped")
    assert failing["narrative"] is None and failing["report_model"] == "none"
    assert numbers(working) == numbers(failing) == numbers(off)
    assert numbers(failing)[2] == -1036 and numbers(failing)[5][0][0] == "promotion"


def test_terra_down_uses_qwen_and_the_run_still_succeeds(monkeypatch, key):
    monkeypatch.setattr(forecast, "_write", Fake(terra="fail", local="ok"))
    body = run()
    assert body["report_model"] == "qwen2.5:7b" and body["writer_status"] == "ok"
    assert [a["outcome"] for a in body["writer_attempts"]] == ["http_500", "ok"]


def test_a_writer_that_crashes_cannot_fail_the_run(monkeypatch):
    def boom(report):
        raise RuntimeError("anything at all")
    monkeypatch.setattr(forecast, "_write", boom)
    body = run()
    assert body["writer_status"] == "fallback_stub" and body["report"]["variance_trx"] == -1036


def test_the_leadership_view_gets_the_prose_without_the_analyst_notes_or_how_it_was_made(monkeypatch, key):
    monkeypatch.setattr(forecast, "_write", Fake(terra="ok"))
    rid = run()["forecast_run_id"]
    assert CLIENT.post(f"/api/forecast/runs/{rid}/submit").status_code == 200
    sign_in("dev-forecast-manager")
    body = CLIENT.get(f"/api/forecast/runs/{rid}").json()
    assert body["view"] == "leadership" and body["narrative"]["summary"]
    assert "analyst_notes" not in body["narrative"] and "writer_attempts" not in body and "stages" not in body
    assert "evidence_ids" not in json.dumps(body)
    preview = CLIENT.get(f"/api/forecast/runs/{rid}").json()
    sign_in("dev-forecast-analyst")
    assert "analyst_notes" in CLIENT.get(f"/api/forecast/runs/{rid}").json()["narrative"]
    assert preview["report_model"] == "gpt-6.1-terra"


def test_the_same_request_again_does_not_spend_another_call(monkeypatch, key):
    fake = Fake(terra="ok")
    monkeypatch.setattr(forecast, "_write", fake)
    first = run()
    second = run()
    assert fake.calls == 1 and second["forecast_run_id"] == first["forecast_run_id"] and second["narrative"] == first["narrative"]


def test_a_run_that_fell_back_is_tried_again_on_a_rerun_and_keeps_its_review(monkeypatch, key):
    failing = Fake(terra="fail", local="fail")
    monkeypatch.setattr(forecast, "_write", failing)
    rid = run()["forecast_run_id"]
    assert CLIENT.post(f"/api/forecast/runs/{rid}/submit").status_code == 200
    sign_in("dev-forecast-manager")
    assert CLIENT.post(f"/api/forecast/runs/{rid}/review", json={"decision": "approved"}).status_code == 200
    recovered = Fake(terra="ok")
    monkeypatch.setattr(forecast, "_write", recovered)
    again = run()
    assert recovered.calls == 1 and again["writer_status"] == "ok" and again["narrative"]
    assert again["forecast_run_id"] == rid and again["review_status"] == "approved"


def test_a_paused_attribution_calls_no_model(monkeypatch, key):
    def never(messages, cfg):
        raise AssertionError("no model should be called for a paused attribution")
    monkeypatch.setattr(forecast, "_write", lambda report: writer.write_report(report, terra=never, local=never))
    body = run(NEW_ENGLAND)
    assert body["writer_status"] == "skipped" and body["narrative"] is None and body["report"]["abstained"] is True


def test_the_writer_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("FEAGENT_WRITER", "off")
    body = run()
    assert body["writer_status"] == "skipped" and body["writer_attempts"][0]["outcome"] == "disabled"


def test_a_run_stored_before_the_writer_existed_still_opens():
    rid = run()["forecast_run_id"]
    from pharmagentics.api import forecast_store
    record = forecast_store.get(rid)
    for k in ("narrative", "report_model", "writer_status", "writer_attempts"):
        record.pop(k)
    forecast_store._put(record)
    body = CLIENT.get(f"/api/forecast/runs/{rid}").json()
    assert body["writer_status"] == "skipped" and body["narrative"] is None and body["report"]["variance_trx"] == -1036


def test_status_says_what_the_writer_would_use_and_never_the_key(monkeypatch, key):
    sign_in("dev-forecast-analyst")
    status = CLIENT.get("/api/forecast/status").json()
    assert status["writer"] == {"enabled": True, "primary": "gpt-6.1-terra", "fallback": "qwen2.5:7b"}
    assert "sk-test-key" not in json.dumps(status)
    monkeypatch.delenv("OPENAI_API_KEY")
    assert CLIENT.get("/api/forecast/status").json()["writer"]["primary"] is None
