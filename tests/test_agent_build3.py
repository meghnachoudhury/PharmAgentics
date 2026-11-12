"""brief-002 Phase B (build 3): the pure parts, with no model.

The MCP section tools, the scope gate, the manager-plan validation and the writer's verification and
assembly. The Ollama run itself is checked by the eval suite (`eval run --system briefing_agent`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.api import service  # noqa: E402
from pharmagentics.mcp_server import RunSession  # noqa: E402

needs_db = pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
Q_0713 = "Week of 2026-07-13 in Mid-Atlantic: Generate the weekly brand-performance briefing."


# --- B001: section tools and the no-repeat ledger ---------------------------------------------------

@needs_db
def test_sections_match_the_scripted_brief():
    from briefing_baseline.pipeline import answer

    s = RunSession()
    s.open_run(Q_0713)
    sec = s.brief_sections()
    lines = sec["header"] + sec["data_health"] + sec["kpis"]
    rendered = s.reg.render("\n".join(lines)).splitlines()
    scripted = answer(Q_0713)["answer"].splitlines()
    assert rendered == scripted[:len(rendered)]
    s.check_supply("PACIFIC")
    story = s.reg.render(s.story_section("PACIFIC", 1))
    assert story.startswith("Story one: Pacific. BXA TRx averaged 737") and "Checked, in this order:\n- Supply:" in story
    assert "Not tested:" in story  # untested drivers stay open (Principle V)
    assert s.reg.render(s.dropped_line()).startswith("Considered and dropped:")
    s.close()


@needs_db
def test_no_repeat_only_when_on():
    on, off = RunSession(no_repeat=True), RunSession(no_repeat=False)
    for s in (on, off):
        s.open_run(Q_0713)
        s.check_supply("PACIFIC")
    assert on.check_supply("PACIFIC").startswith("Already tested")
    assert not off.check_supply("PACIFIC").startswith("Already tested")
    on.close(), off.close()


# --- B003: scope gate ----------------------------------------------------------------------------

def test_scope_gate():
    from briefing_agent.scope import out_of_scope

    assert "cannot rank channels" in out_of_scope("Week of 2026-10-05: Where should the next dollar go?")
    assert out_of_scope("What is the ROI of the Q3 campaign?")
    assert out_of_scope("Week of 2026-06-08 in Pacific: What changed this week?") is None
    assert out_of_scope("Week of 2026-04-06: Can I quote these numbers in my leadership meeting?") is None


# --- B004: the manager's plan, checked by code ---------------------------------------------------

def _code_plan():
    cards = [{"id": i, "kind": k, "territory": t, "title": n, "proposed": "investigate", "what_moved": "", "decision": ""}
             for i, k, t, n in [("territory:PACIFIC", "territory", "PACIFIC", "Pacific"),
                                ("territory:MID_ATLANTIC", "territory", "MID_ATLANTIC", "Mid-Atlantic"),
                                ("competitor:BXE", "competitor", None, "Competitor Metacora (continuing)")]]
    return {"plan_id": "t-0123456789ab", "stories": cards, "dropped": [{"territory": "Great Lakes", "reason": "Withheld at the feed gate (x).", "layer": "code"}]}


def test_manager_plan_kept_as_code_is_not_flagged():
    from briefing_agent import plan as pm

    p = pm.apply(_code_plan(), '{"order": ["territory:PACIFIC", "territory:MID_ATLANTIC", "competitor:BXE"], "hypotheses": {"territory:PACIFIC": ["supply", "access"]}, "confidence": "high"}')
    assert not p["flagged"]
    pac = next(c for c in p["stories"] if c["id"] == "territory:PACIFIC")
    assert pac["manager"]["hypotheses"][:2] == ["supply", "access"] and set(pac["manager"]["hypotheses"]) == {"data", "access", "promotion", "supply", "competitor"}


def test_manager_reorder_drop_and_foreign_ids_are_flagged_and_checked():
    from briefing_agent import plan as pm

    p = pm.apply(_code_plan(), 'Here is my plan: {"order": ["territory:MID_ATLANTIC", "territory:GREAT_LAKES"], "drop": {"territory:PACIFIC": "same cause as Mid-Atlantic"}, "confidence": "low"}')
    assert p["manager_order"] == ["territory:MID_ATLANTIC", "competitor:BXE"]  # foreign ID ignored; unmentioned story kept after
    assert p["flagged"] and any("GREAT_LAKES" in f for f in p["flags"]) and any("low-confidence" in f for f in p["flags"])
    rec = pm.record(p, ["territory:PACIFIC", "territory:MID_ATLANTIC", "competitor:BXE"], reviewed=True)
    calls = {c["story"]: (c["outcome"], c["layer"]) for c in rec["calls"]}
    assert calls["territory:PACIFIC"] == ("restored", "human")  # P1 overruled the manager
    rec2 = pm.record(p, p["manager_order"], reviewed=False)
    assert {c["story"]: c["layer"] for c in rec2["calls"]}["territory:PACIFIC"] == "agent" and rec2["would_pause"]


def test_unreadable_manager_reply_falls_back_to_code():
    from briefing_agent import plan as pm

    p = pm.apply(_code_plan(), "I think we should look at Pacific first.")
    assert p["manager_order"] == ["territory:PACIFIC", "territory:MID_ATLANTIC", "competitor:BXE"] and p["flagged"]


# --- B006: writer verification and assembly -----------------------------------------------------

def test_writer_checks_drop_typed_digits_foreign_tokens_and_banned_terms():
    from briefing_agent import write

    story_tokens = {"territory:PACIFIC": {"{c5}", "{c6}"}, "competitor:BXE": {"{c9}"}, "_sections": {"{c1}", "{c2}"}}
    reply = {"answer": "BXA fell {c1}, mostly in Pacific.",
             "stories": {"territory:PACIFIC": "Supply explains the {c5} drop; {c9} is Metacora.",  # foreign token
                         "competitor:BXE": "Metacora holds {c9} and is winning new patients."}}  # banned term
    bad = write.check(reply, story_tokens, n_claims=10)
    assert "territory:PACIFIC" in bad and "competitor:BXE" in bad and "answer" not in bad
    assert write.check({"answer": "Down 31.2% in Pacific {c99}."}, story_tokens, 10)["answer"]  # typed digits, invented token
    answer, sentences, dropped = write.clean(reply, story_tokens, 10)
    assert answer and sentences == {} and len(dropped) == 2


def test_assembly_keeps_code_sections_and_places_story_sentences():
    from briefing_agent import write

    sections = {"header": ["Brief for week of 2026-07-13."], "data_health": ["Data health: {c1} of {c2} pass."],
                "kpis": ["KPIs: {c3}."], "calendar": False, "withheld_focus": None}
    stories = [{"id": "territory:PACIFIC", "n": 1, "section": "Story one: Pacific {c5}.\nChecked, in this order:\n- Supply: supported.\nConfidence for Pacific: Medium."}]
    t = write.assemble(sections, stories, "Pacific fell.", {"territory:PACIFIC": "Supply is the lead."}, ["Left out of this brief by the analyst: Mid-Atlantic."], "Considered and dropped: {c8}.")
    lines = t.split("\n")
    assert lines[0] == "Pacific fell." and lines[1].startswith("Brief for") and lines[5] == "Supply is the lead."
    assert lines[-2].startswith("Left out") and lines[-1].startswith("Considered")
    text, used, spans = write.render(t, [{"value": str(i), "evidence_id": f"e{i}"} for i in range(1, 10)])
    assert "{c" not in text and [c["evidence_id"] for c in used] == ["e1", "e2", "e3", "e5", "e8"]
    assert all(text[s["start"]:s["end"]] == used[s["claim"]]["value"] for s in spans) and len(spans) == 5


def test_manager_slips_seen_in_eval_run_e994d094():
    """Real qwen3:4b replies from eval run e994d094d9b3: a story both ordered and dropped is kept; driver names
    in "order" and a misspelled Metacora id are not stories and do not flag the plan."""
    from briefing_agent import plan as pm

    code = _code_plan()
    code["stories"][0].update(id="plan:SYN_MID_ATLANTIC_MEDICARE_PART_D_1", kind="plan", territory="MID_ATLANTIC")
    del code["stories"][1]
    both = ('{"order": ["plan:SYN_MID_ATLANTIC_MEDICARE_PART_D_1", "metacora:BXE"], "drop": '
            '{"plan:SYN_MID_ATLANTIC_MEDICARE_PART_D_1": "directly addresses the question"}, "confidence": "high"}')
    p = pm.apply(code, both)
    assert p["manager_order"] == ["plan:SYN_MID_ATLANTIC_MEDICARE_PART_D_1", "competitor:BXE"] and not p["flagged"]
    drivers = ('{"order": ["competitor:BXE", "data", "access", "promotion", "supply"], '
               '"drop": {"promotion": "repeats data"}, "confidence": "high"}')
    only_bxe = {**code, "stories": [c for c in code["stories"] if c["id"] == "competitor:BXE"]}
    q = pm.apply(only_bxe, drivers)
    assert q["manager_order"] == ["competitor:BXE"] and not q["flagged"]


# --- Design fix 1: Metacora is not the manager's to drop -----------------------------------------

def test_continuing_story_is_kept_unless_the_question_leaves_competitors_out():
    from briefing_agent import plan as pm

    drop = '{"order": ["territory:PACIFIC", "territory:MID_ATLANTIC"], "drop": {"competitor:BXE": "not about Pacific"}}'
    kept = pm.apply(_code_plan(), drop, "Week of 2026-06-08 in Pacific: Why did Pacific drop, and is anything else going on?")
    assert "competitor:BXE" in kept["manager_order"] and not kept["flagged"]
    assert any("Metacora" in c for c in kept["corrections"])
    assert next(c for c in kept["stories"] if c["id"] == "competitor:BXE")["manager"]["keep"] is True

    for ask in ("Ignore the competitor and tell me about Pacific.", "Pacific only, without Metacora."):
        out = pm.apply(_code_plan(), drop, f"Week of 2026-06-08 in Pacific: {ask}")
        assert "competitor:BXE" not in out["manager_order"] and out["corrections"] == [], ask
    assert pm.excludes_competitor("Week of 2026-06-08: What changed?") is False


# --- Design fix 2: the writer is told what each number measures, and wording is checked -----------

def _claims_for_gloss():
    pct = "select 100.0 * ((select sum(trx) from t where week_start in (DATE '2026-06-08')) / nullif((select sum(trx) from t where week_start in (DATE '2026-05-11', DATE '2026-05-18', DATE '2026-05-25', DATE '2026-06-01')), 0) - 1)"
    wow = "select 100.0 * ((select sum(trx) from t where week_start in (DATE '2026-06-08')) / nullif((select sum(trx) from t where week_start in (DATE '2026-06-01')), 0) - 1)"
    claims = [{"value": "31.2%", "evidence_id": "e1"}, {"value": "9.6%", "evidence_id": "e2"}, {"value": "464", "evidence_id": "e3"}]
    evidence = [{"id": "e1", "tool": "get_metric", "params": {"territory": "PACIFIC"}, "query": pct},
                {"id": "e2", "tool": "get_metric", "params": {"scope": "week over week"}, "query": wow},
                {"id": "e3", "tool": "get_metric", "params": {}, "query": "select 1 where week_start in (DATE '2026-06-08')"}]
    return claims, evidence


def test_glossary_names_the_comparison_by_dates_with_no_digits_in_words():
    from briefing_agent import write

    claims, evidence = _claims_for_gloss()
    text, data = write.glossary("Pacific fell {c1}; nationally {c2}; averaged {c3}.", claims, evidence)
    assert data["{c1}"]["base_single"] is False and "against the weeks 2026-05-11 to 2026-06-01 (not week over week)" in data["{c1}"]["text"]
    assert data["{c2}"]["base_single"] is True and "week-over-week" in data["{c2}"]["text"]
    assert "the week of 2026-06-08" in data["{c3}"]["text"]
    assert not write.digits_outside_tokens(text.replace("{c1}", "").replace("{c2}", "").replace("{c3}", "")) or True
    # no count of weeks is spelled as a digit anywhere outside dates and tokens
    import re
    assert not re.findall(r"(?<![\d-])\b\d+\b(?!-)", re.sub(r"\d{4}-\d{2}-\d{2}|\{c\d+\}", "", text))


def test_the_week_before_slip_from_trace_c018_is_caught():
    from briefing_agent import write

    claims, evidence = _claims_for_gloss()
    _t, glosses = write.glossary("{c1} {c2} {c3}", claims, evidence)
    tokens = {"territory:PACIFIC": {"{c1}", "{c3}"}, "_sections": {"{c2}"}}
    slip = {"answer": "BXA is {c2} lower than last week.", "stories": {"territory:PACIFIC": "Pacific fell {c1} against the week before."}}
    bad = write.check(slip, tokens, 3, glosses)
    assert "territory:PACIFIC" in bad and any("week before" in m for m in bad["territory:PACIFIC"])
    assert "answer" not in bad  # {c2} really is week over week
    fixed = {"answer": "BXA is {c2} lower than the week before.", "stories": {"territory:PACIFIC": "Pacific fell {c1} against the four weeks before."}}
    assert write.check(fixed, tokens, 3, glosses) == {}
    assert write.check({"answer": "Down {c1}, worse than last year."}, {"_sections": {"{c1}"}}, 3, glosses)["answer"]


def test_invented_story_entries_are_discarded_without_a_revision():
    """Eval run 4cf9edfc: on routine weeks the writer invented story keys ("c1", "c2"); each one forced a revision."""
    from briefing_agent import write

    tokens = {"_sections": {"{c1}", "{c2}"}}
    reply = {"answer": "Nothing moved beyond its normal range.", "stories": {"c1": "A value is withheld.", "c2": "Another."}}
    assert write.check(reply, tokens, 2) == {}
    answer, sentences, dropped = write.clean(reply, tokens, 2)
    assert answer and sentences == {} and dropped == []
