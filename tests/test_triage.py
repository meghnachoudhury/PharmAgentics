"""brief-002 Phase A: the code triage plan, P1's decision, and the stage flow (US7, US8).

Runs the real scripted baseline on the loaded release. No model.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.api import service  # noqa: E402

pytestmark = pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")

FIXTURE = ROOT / "tests" / "fixtures" / "scripted_answers.json"


def q(week: str, territory: str | None = None) -> str:
    return f"Week of {week}" + (f" in {territory}" if territory else "") + ": Generate the weekly brand-performance briefing."


def comparable(envelope: dict) -> dict:
    """The envelope's answer, claims, evidence and flag, with this machine's data version replaced by a
    placeholder: the version is a hash of the data files, so the frozen fixture must not depend on it."""
    text = json.dumps({k: envelope[k] for k in ("answer", "claims", "evidence", "abstained")}, default=str)
    return json.loads(_mask_version(text))


def _mask_version(text: str) -> str:
    m = re.search(r"Data version ([0-9a-f]{12})", text) or re.search(r'"data_version": "([0-9a-f]{12})"', text)
    return text.replace(m.group(1), "<DATA_VERSION>") if m else text


# --- T003: the split changes nothing ---------------------------------------------------------------

def test_answer_unchanged():
    from briefing_baseline.pipeline import answer

    for question, expected in json.loads(FIXTURE.read_text(encoding="utf-8")).items():
        masked = json.loads(_mask_version(json.dumps(expected)))  # the fixture was frozen on another data version
        assert comparable(answer(question)) == masked, question


# --- US8: the code triage plan and P1's decision ---------------------------------------------------

def _plan(week, territory=None):
    from briefing_baseline.pipeline import triage

    return triage(q(week, territory))


def test_plan_2026_06_08_proposes_pacific_then_metacora():
    plan = _plan("2026-06-08", "Pacific")
    assert plan["state"] == "TRIAGE_REVIEW"
    assert [(c["id"], c["proposed"]) for c in plan["stories"]] == [("territory:PACIFIC", "investigate"), ("competitor:BXE", "investigate")]
    quiet = [d["territory"] for d in plan["dropped"] if d["reason"].startswith("Within")]
    assert len(quiet) == 7 and all(d["layer"] == "code" for d in plan["dropped"])
    for card in plan["stories"]:
        assert all(card[k] for k in ("what_moved", "decision", "population", "granularity", "time"))


def test_withheld_territory_is_dropped_by_code_and_cannot_be_added():
    from briefing_baseline.pipeline import run_with_plan

    plan = _plan("2026-05-04", "New England")
    withheld = {d["territory"]: d["reason"] for d in plan["dropped"] if d["reason"].startswith("Withheld")}
    assert "New England" in withheld and "late delivery" in withheld["New England"]
    with pytest.raises(ValueError, match="territory:NEW_ENGLAND"):
        run_with_plan(plan["question"], {"plan_id": plan["plan_id"], "stories": ["territory:NEW_ENGLAND"]})


def test_default_decision_equals_answer():
    from briefing_baseline.pipeline import answer, run_with_plan

    for week, territory in (("2026-06-08", "Pacific"), ("2026-07-13", "Mid-Atlantic")):
        plan = _plan(week, territory)
        ids = [c["id"] for c in plan["stories"] if c["proposed"] == "investigate"]
        run = run_with_plan(plan["question"], {"plan_id": plan["plan_id"], "stories": ids})
        assert comparable(run["envelope"]) == comparable(answer(plan["question"]))
        assert run["triage"]["default"] is True


def test_dropping_and_reordering_stories():
    from briefing_baseline.pipeline import run_with_plan

    plan = _plan("2026-07-13", "Mid-Atlantic")
    dropped = run_with_plan(plan["question"], {"plan_id": plan["plan_id"], "stories": ["territory:PACIFIC", "competitor:BXE"]})
    text = dropped["envelope"]["answer"]
    assert "Story two: Mid-Atlantic" not in text and "Story two: competitor Metacora" in text
    assert "Left out of this brief by the analyst: Mid-Atlantic." in text
    call = next(c for c in dropped["triage"]["calls"] if c["story"] == "territory:MID_ATLANTIC")
    assert (call["outcome"], call["layer"]) == ("dropped", "human")

    moved = run_with_plan(plan["question"], {"plan_id": plan["plan_id"], "stories": ["territory:MID_ATLANTIC", "territory:PACIFIC", "competitor:BXE"]})
    assert moved["envelope"]["answer"].index("Story one: Mid-Atlantic") < moved["envelope"]["answer"].index("Story two: Pacific")
    assert any(c["outcome"] == "moved" and c["layer"] == "human" for c in moved["triage"]["calls"])


def test_stale_plan_is_refused():
    from briefing_baseline.pipeline import StalePlan, run_with_plan

    with pytest.raises(StalePlan):
        run_with_plan(q("2026-06-08", "Pacific"), {"plan_id": "t-000000000000", "stories": []})


def test_cards_carry_numbers_only_as_claims_and_routine_week_has_no_cards():
    plan = _plan("2026-06-08", "Pacific")
    evidence = {e["id"]: e for e in plan["evidence"]}
    assert plan["claims"] and all(c["evidence_id"] in evidence for c in plan["claims"])
    assert all(e["data_version"] == plan["data_version"] for e in plan["evidence"])
    values = {c["value"] for c in plan["claims"]}
    for card in plan["stories"]:
        for k in ("what_moved", "decision", "population", "granularity", "time"):
            # every number on a card is a claim value or part of a date
            for number in re.findall(r"(?<![\d-])\d[\d,.]*%?", re.sub(r"\d{4}-\d{2}-\d{2}", "", card[k])):
                assert number.rstrip(".") in values, (k, number)
    routine = _plan("2025-04-21")
    assert routine["state"] == "ROUTINE" and routine["stories"] == []


# --- US7: the stage flow ---------------------------------------------------------------------------

def test_stage_flow_names_who_acted():
    from briefing_baseline.pipeline import run_with_plan
    from briefing_baseline.triage import stage_flow

    plan = _plan("2026-05-04", "New England")
    run = run_with_plan(plan["question"], {"plan_id": plan["plan_id"], "stories": ["competitor:BXE"]})
    flow = run["flow"]
    assert [s["stage"] for s in flow] == [1, 2, 3, 4, 5, 6, 7]
    assert flow[1]["states"] == ["VALIDATION_WARNING"] and "New England" in flow[1]["note"]
    assert flow[2]["states"] == ["INVESTIGATION_REQUESTED"]
    assert flow[3]["states"] == ["TRIAGE_REVIEW", "INVESTIGATING", "EVIDENCE_RECEIVED"]
    assert [a["kind"] for a in flow[3]["actors"]] == ["code", "human", "code"]
    assert "manager off" in flow[3]["actors"][2]["name"]

    routine = stage_flow(_plan("2025-04-21"), None, verified=True)
    assert routine[2]["states"] == ["ROUTINE"] and routine[3]["states"] == []


# --- Inline citations: every span points at its claim's value -------------------------------------

def test_citations_point_at_their_claims():
    from briefing_baseline.pipeline import answer

    env = answer(q("2026-06-08", "Pacific"))
    spans = env["citations"]
    assert spans and all(env["answer"][s["start"]:s["end"]] == env["claims"][s["claim"]]["value"] for s in spans)
    assert [s["start"] for s in spans] == sorted(s["start"] for s in spans)
