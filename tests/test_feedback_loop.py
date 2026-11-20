"""core-008 FR-019 to FR-022: the feedback loop proposes, people promote (ADR 0003). No model is called: drafting,
rerunning, reviewing and gating are replaced, so these tests check the rules, the storage and the access."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))
sys.path.insert(0, str(ROOT))

from eval.harness import improve, promote  # noqa: E402
from pharmagentics.api import store  # noqa: E402
from pharmagentics.api.app import app  # noqa: E402


def vote(ref: str, kind: str, comment: str | None, ts: str) -> dict:
    return {"lane": "briefing", "ref": ref, "vote": kind, "view": "analyst", "comment": comment, "ts": ts,
            "personas": ["P1"], "engine": "agent", "system": "briefing_agent", "data_version": "x",
            "scope": {"question": "Week of 2026-06-08 in Pacific: brief", "brand_id": "BXA", "territory_id": "PACIFIC",
                      "week_start": "2026-06-08"}, "shown": "Pacific fell 31.2% because of supply."}


@pytest.fixture
def state(tmp_path):
    for i, v in enumerate([vote("b-aaaaaaaaaaaa", "down", "It called a Medium story a cause.", "2026-11-19T10:00:00"),
                           vote("b-bbbbbbbbbbbb", "up", None, "2026-11-19T11:00:00")]):
        p = tmp_path / "feedback" / "response" / "briefing" / v["ref"] / f"u{i}-analyst.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(v), encoding="utf-8")
    t = tmp_path / "threads" / "b-cccccccccccc" / "0123456789ab.json"
    t.parent.mkdir(parents=True)
    t.write_text(json.dumps({"brief_id": "b-cccccccccccc", "owner": "0123456789ab", "saved": True,
                             "turns": [{"question": "Split §3.1 by plan", "section": "3.1", "answer": "Not in this brief."}]}))
    return tmp_path


def fake_model(monkeypatch, lesson="Use association wording for any story below High confidence.", resolved=True,
               checks=True, gate=True):
    monkeypatch.setattr(improve, "draft_lesson", lambda spec, v: lesson)
    monkeypatch.setattr(improve, "rerun", lambda q, lessons, spec: {"answer": "Pacific fell, associated with supply."})
    monkeypatch.setattr(improve, "gated_ok", lambda env: checks)
    monkeypatch.setattr(improve, "review", lambda spec, comment, answer: (resolved, "The causal wording is gone."))
    monkeypatch.setattr(improve, "gate_with", lambda lessons, baseline, spec: gate)


def test_lesson_code_checks():
    assert improve.lesson_problems("Use association wording below High confidence.") == []
    assert "holds a digit" in improve.lesson_problems("Check the top 3 plans first.")
    assert any("surveillance" in p for p in improve.lesson_problems("Run statistical surveillance first."))
    assert any("new patients" in p for p in improve.lesson_problems("Report new patients from NRx."))
    assert improve.lesson_problems("") == ["empty"]


def test_confident_only_when_every_condition_holds():
    assert improve.decide([], True, True, True) == (True, [])
    for args in (([], False, True, True), ([], True, False, True), ([], True, True, False), ([], True, True, None),
                 (["holds a digit"], True, True, True), ([], None, None, None)):
        confident, reasons = improve.decide(*args)
        assert not confident and reasons


def test_improve_proposes_lessons_and_cases_once(state, monkeypatch):
    fake_model(monkeypatch)
    made = improve.run(state, baseline="run-1", model="anthropic:claude-haiku-5-5")
    kinds = sorted((p["kind"], p["source"].split(":")[0]) for p in made)
    assert kinds == [("case", "thread"), ("case", "upvote"), ("lesson", "vote")]
    lesson = next(p for p in made if p["kind"] == "lesson")
    assert lesson["confident"] and lesson["status"] == "proposed" and not lesson["reasons"]
    assert all(not p["confident"] for p in made if p["kind"] == "case")  # a vote is never proof
    stored = list((state / "review" / "proposals").glob("*.json"))
    assert len(stored) == 3
    assert improve.run(state, baseline="run-1") == []  # nothing new the second time


def test_without_a_gate_or_with_a_number_nothing_is_confident(state, monkeypatch):
    fake_model(monkeypatch, lesson="Check the top 3 plans first.")
    lesson = next(p for p in improve.run(state, baseline=None) if p["kind"] == "lesson")
    assert not lesson["confident"] and "holds a digit" in lesson["reasons"] and lesson["after"] == ""  # never rerun


@pytest.fixture
def signed(monkeypatch, state):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(state))
    monkeypatch.delenv("K_SERVICE", raising=False)

    def login(user: str) -> TestClient:
        c = TestClient(app)
        c.post("/auth/dev-login", data={"username": user}, follow_redirects=False)
        return c
    return login


def test_only_the_tester_admin_sees_and_decides(state, monkeypatch, signed):
    fake_model(monkeypatch)
    lesson = next(p for p in improve.run(state, baseline="run-1") if p["kind"] == "lesson")
    for user in ("dev-analyst", "dev-director", "dev-forecast-analyst", "dev-forecast-manager"):
        assert signed(user).get("/api/review/proposals").status_code == 404
        assert signed(user).post(f"/api/review/proposals/{lesson['id']}", json={"decision": "approve"}).status_code == 404
    tester = signed("dev-tester")
    assert {p["id"] for p in tester.get("/api/review/proposals").json()} >= {lesson["id"]}
    done = tester.post(f"/api/review/proposals/{lesson['id']}", json={"decision": "approve", "note": "ok"}).json()
    assert done["status"] == "approved" and done["decided_at"]
    events = store.backend().keys("events/")
    assert not any("review" in k for k in events)  # not a UAT event


def test_promote_writes_approved_lessons_and_cases_and_prints_git(state, monkeypatch, tmp_path):
    fake_model(monkeypatch)
    made = improve.run(state, baseline="run-1")
    backend = store.LocalBackend(state)
    for p in made:
        key = f"review/proposals/{p['id']}.json"
        doc = json.loads(backend.read(key))
        doc.update(status="approved", decided_by="Dev test view", decided_at="2026-11-20T05:00:00Z")
        backend.write(key, json.dumps(doc))
    lessons_file = tmp_path / "lessons.yaml"
    lessons_file.write_text("lessons: []\n", encoding="utf-8")
    out = promote.run(state, lessons_file=lessons_file, candidates_dir=tmp_path / "candidates", today="2026-11-20")
    assert len(out["lessons"]) == 1 and len(out["cases"]) == 2 and out["git"][0] == "git switch -c lessons/2026-11-20"
    data = yaml.safe_load(lessons_file.read_text(encoding="utf-8"))
    assert data["lessons"][0]["text"].startswith("Use association wording")
    assert all(json.loads(backend.read(f"review/proposals/{p['id']}.json"))["status"] == "promoted" for p in made)
    assert promote.run(state, lessons_file=lessons_file, candidates_dir=tmp_path / "candidates")["lessons"] == []


def test_agents_read_only_approved_lessons(monkeypatch, tmp_path):
    from briefing_agent import lessons
    f = tmp_path / "lessons.yaml"
    f.write_text("lessons: []\n", encoding="utf-8")
    monkeypatch.setattr(lessons, "FILE", f)
    monkeypatch.delenv(lessons.TRIAL, raising=False)
    assert lessons.block() == ""  # no lesson: the prompt is unchanged
    f.write_text(yaml.safe_dump({"lessons": [{"id": "p-1", "text": "Name the restated week first.", "applies_to": "writer"},
                                             {"id": "p-2", "text": "Check 3 plans.", "applies_to": "writer"}]}), encoding="utf-8")
    assert "Name the restated week first." in lessons.block() and "Check 3 plans" not in lessons.block()
    monkeypatch.setenv(lessons.TRIAL, json.dumps(["Say which cut is projected."]))
    assert "Say which cut is projected." in lessons.block()
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "agents" / "brand-briefing" / "briefing_agent").glob("*.py"))
    assert "threads/" not in code and "feedback/response" not in code and "review/proposals" not in code  # FR-022
