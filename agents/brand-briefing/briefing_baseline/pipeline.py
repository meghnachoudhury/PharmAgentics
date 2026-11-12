"""Briefing lane, scripted baseline (Evaluation Pack §6): a fixed pipeline with a fixed order of
checks and a templated brief. No model. Stages follow the System Architecture spine:

1 load and pin -> 2 validation gate -> 3a competitive intelligence -> 4a fixed-order investigation
-> 5 template narrative (claim tokens) -> 6 verification (no digit outside a claim token).

The stage steps live in `pharmagentics.tools.stages`, shared with the MCP tools the low-code agent
calls, so this pipeline stays the manager-off ablation: same tools, fixed order.

brief-002 Phase A splits the run at the end of stage 3. `answer(question)` runs straight through
with the default triage, exactly as before (the eval entry point). `triage(question)` stops after
stage 3 and returns the triage plan for P1; `run_with_plan(question, decision)` runs stages 4 to 6
on the stories P1 approved, in P1's order.
"""
from __future__ import annotations

from dataclasses import dataclass

from pharmagentics.tools import DEFAULT_DB, Registry
from pharmagentics.tools import stages
from pharmagentics.tools.checks import OWNER, confidence, run_checks
from pharmagentics.tools.queries import name
from pharmagentics.tools.registry import digits_outside_tokens
from pharmagentics.tracing import finish, span

MAX_STORIES = 4
COMPETITOR = "competitor:BXE"


class StalePlan(ValueError):
    """The decision's plan_id no longer matches the plan code builds now."""


@dataclass
class Front:
    """What stages 1 to 3 produced: the period, the brief's lines so far and the screen."""
    p: stages.Period
    out: list[str]
    found: list[dict]
    quiet: list[str]


def answer(question: str, db=DEFAULT_DB) -> dict:
    reg = Registry(db)
    try:
        return _brief(reg, question)
    finally:
        reg.close()


def triage(question: str, db=DEFAULT_DB) -> dict:
    """Stages 1 to 3, then the code triage plan for P1 (brief-002 US8). Its claims are its own run's."""
    from .triage import build_plan

    reg = Registry(db)
    try:
        f = _front(reg, question)
        if f is None:
            raise ValueError("That period is outside the release.")
        return build_plan(reg, f)
    finally:
        reg.close()


def run_with_plan(question: str, decision: dict, db=DEFAULT_DB) -> dict:
    """Stages 4 to 6 on P1's decision: {plan_id, stories: [ids in order]}. Returns the envelope, the
    triage record (who made each call) and the stage flow."""
    from .triage import stage_flow, triage_record

    plan = triage(question, db)  # recomputed by code, in its own registry, so the brief's claim numbering is untouched
    if decision.get("plan_id") != plan["plan_id"]:
        raise StalePlan("The triage plan changed; review it again.")
    allowed = [c["id"] for c in plan["stories"] if c["proposed"] == "investigate"]
    order = list(decision.get("stories", []))
    bad = [s for s in order if s not in allowed] or [s for s in set(order) if order.count(s) > 1]
    if bad:
        raise ValueError(f"Not a story this plan proposes for investigation: {', '.join(sorted(set(bad)))}")
    titles = {c["id"]: c["title"] for c in plan["stories"]}
    left_out = [titles[s] for s in allowed if s not in order]
    reg = Registry(db)
    try:
        envelope = _brief(reg, question, order=order, left_out=left_out)
    finally:
        reg.close()
    record = triage_record(plan, order)
    return {"envelope": envelope, "triage": record, "flow": stage_flow(plan, record, verified=True)}


def story_id(s: dict) -> str:
    return f"plan:{s['plan']}" if s["kind"] == "plan" else f"territory:{s['territory']}"


def default_order(found: list[dict]) -> list[str]:
    return [story_id(s) for s in found[:MAX_STORIES]] + [COMPETITOR]


def _front(reg: Registry, question: str) -> Front | None:
    p = stages.resolve(reg, question)
    if not p.requested:
        return None
    out: list[str] = []

    with span("1_load_and_pin", inputs={"question": question}, data_version=reg.data_version) as sp:
        out.append(f"Brief for {stages.describe(p)}. "
                   f"Data version {reg.data_version}. Product: BXA. Territory questions use only cuts that pass the feed gate.")
        if p.note:
            out.append(p.note)
        finish(sp, {"weeks": p.requested, "baseline_weeks": p.baseline, "territory": p.focus, "data_version": reg.data_version})

    with span("2_validation_gate") as sp:
        out.append(stages.data_health(reg, p))
        out += stages.restatements(reg, p)  # EV-1.2
        finish(sp, {"like_for_like_territories": p.ok})

    with span("3a_competitive_intelligence") as sp:
        if p.calendar_note:
            out.append(p.calendar_note)
        out += stages.kpis(reg, p)
        found, quiet = ([], []) if p.calendar else stages.screen(reg, p)
        finish(sp, {"calendar_mode": bool(p.calendar), "candidates": [f["territory"] for f in found]})
    return Front(p, out, found, quiet)


def _brief(reg: Registry, question: str, order: list[str] | None = None, left_out: list[str] = ()) -> dict:
    f = _front(reg, question)
    if f is None:
        return _envelope(reg, stages.outside_release(stages.resolve(reg, question)), False)
    p, out = f.p, f.out
    abstained = False

    with span("4a_investigation") as sp:
        if p.calendar:
            out.append("No story is opened for a calendar week. Expect a rebound in the next regular week.")
        else:
            if p.focus in p.terrs and p.focus not in p.ok:
                out.append(f"{name(p.focus)} has withheld cuts in these weeks, so no like-for-like story is given for it.")
            by_id = {story_id(s): s for s in f.found}
            shown = 0
            for sid in (default_order(f.found) if order is None else order):
                if sid == COMPETITOR:
                    comp = stages.competitor_status(reg, p, lead=f"Story {_ord(shown + 1)}: competitor Metacora")
                    if comp:
                        out.append(comp)
                        shown += 1
                    continue
                s = by_id[sid]
                shown += 1
                with span(f"story_{shown}_{s['territory']}", inputs={"territory": s["territory"], "kind": s["kind"]}) as story_sp:
                    text, abst = _story(reg, shown, s, p)
                    finish(story_sp, {"abstained": abst})
                out.append(text)
                abstained |= abst
            if left_out:
                out.append(f"Left out of this brief by the analyst: {', '.join(left_out)}.")
            if shown == 0 and not left_out:
                out.append("Routine week. No material change was found, and territory swings stayed in their normal range.")
            elif f.quiet:
                out.append(f"Considered and dropped: {stages.dropped_count(reg, p, f.quiet)} territories moved within their normal range.")
        finish(sp, {"abstained": abstained})

    with span("5_narrative") as sp:
        template = "\n".join(x for x in out if x)
        finish(sp, {"template_chars": len(template), "claims": len(reg.claims)})

    with span("6_verification") as sp:
        bad = digits_outside_tokens(template)
        finish(sp, {"digits_outside_tokens": bad})
        if bad:
            raise AssertionError(f"digit outside a claim token: {bad[:3]}")
    return _envelope(reg, reg.render(template), abstained)


def _story(reg, n, s, p):
    t = s["territory"]
    checks = run_checks(reg, t, p.weeks, p.baseline)
    level, lead = confidence(checks)
    head = f"Story {_ord(n)}: {stages.territory_change(reg, p, t)}"
    lines = [head, "Checked, in this order:"] + [f"- {c.text}" for c in checks]
    supported = [c for c in checks if c.verdict == "supported"]
    abstain = level == "Low"
    if abstain:
        lines.append(f"Confidence: {level}. Unresolved, investigate next. No driver is named. Next: split {name(t)} by plan and specialty, and ask sales leadership for local context.")
    else:
        verb = "Leading driver" if level == "High" else "Candidate drivers"
        owner = ", ".join(OWNER[c.driver] for c in supported)
        lines.append(f"Confidence: {level}. {verb}: {lead}. Next: involve {owner}.")
    return "\n".join(lines), abstain


def _ord(n: int) -> str:
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}[n]


def _envelope(reg: Registry, text: str, abstained: bool) -> dict:
    return {"system": "briefing_scripted", "answer": text, "claims": reg.claims, "evidence": reg.evidence, "abstained": abstained}
