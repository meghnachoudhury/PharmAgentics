"""brief-002 Phase A: the code triage plan P1 reviews, the record of who made each call, and the
stage flow shown with the brief. Types in specs/brief-002-triage-investigation/data-model.md.

Every number on a card is a claim from this run's registry (shared Principle I); counts are written
as names. Each card answers the first four questions of the course's five-question triage
(docs/planning/data-plan-triage.md): Decision, Population, Granularity, Time.
"""
from __future__ import annotations

import hashlib

from pharmagentics.tools import queries as qy
from pharmagentics.tools import stages
from pharmagentics.tools.checks import launch_date
from pharmagentics.tools.registry import digits_outside_tokens

from .pipeline import COMPETITOR, MAX_STORIES, Front, story_id

INVESTIGATE_ACTION = ("Investigate: a data check first, then access, promotion, supply and competitor, "
                      "in a fixed order (manager off).")


def _names(territories) -> str:
    return ", ".join(qy.name(t) for t in territories) or "none"


def _time(p) -> str:
    W, B = p.weeks, p.baseline
    weeks = f"week of {W[0]}" if len(W) == 1 else f"weeks {W[0]} to {W[-1]}"
    base = f"; baseline {B[0]} to {B[-1]}" if B else ""
    text = weeks + base + "." + (" Calendar weeks are left out of the stories." if p.calendar_note else "")
    return text[0].upper() + text[1:]


def _population(p) -> str:
    withheld = [t for t in p.terrs if t not in p.ok]
    text = f"Like-for-like territories (every week passes the feed gate): {_names(p.ok)}."
    return text + (f" Withheld: {_names(withheld)}." if withheld else "")


def _card(reg, f: Front, s: dict | None, rank: int, proposed: str) -> dict:
    p = f.p
    if s is None:  # the continuing competitor story
        launched = launch_date(reg)
        share = reg.claim("compare_competitors", qy.share(p.weeks, "BXE"), "pct1", product="BXE")
        return {
            "id": COMPETITOR, "kind": "competitor", "title": "Competitor Metacora (continuing)", "rank": rank,
            "proposed": proposed,
            "what_moved": f"Metacora (launched {launched}) held {share} of the four-brand basket in these weeks.",
            "decision": (f"A continuing story since launch on {launched}; code links it instead of rediscovering it. "
                         "Report its status: share of the basket, weeks since launch and direction."),
            "population": "Every territory's four-brand basket.",
            "granularity": "National basket of four brands.",
            "time": _time(p),
        }
    t = s["territory"]
    if s["kind"] == "plan":
        x, b = qy.mean_weekly(p.weeks, plan=s["plan"]), qy.mean_weekly(p.baseline, plan=s["plan"])
        change = reg.scalar(qy.pct_change(x, b)) or 0
        moved = (f"Plan {s['plan']} in {qy.name(t)}: BXA TRx averaged {reg.claim('get_metric', x, 'int', plan=s['plan'])} a week "
                 f"against {reg.claim('get_metric', b, 'int', plan=s['plan'])} before "
                 f"({stages.word(change)} {reg.claim('get_metric', qy.pct_change(x, b), 'pct1', plan=s['plan'])}).")
        why = "A payer access change on this plan, and its BXA TRx moved past the plan-level threshold (code screen)."
        grain = f"Plan {s['plan']}, in {qy.name(t)}."
    else:
        moved = stages.territory_change(reg, p, t)
        why = ("The question names this territory, so code always proposes it." if t == p.focus else
               "Its change is beyond its own normal range and beyond the other territories' change (code screen).")
        grain = f"Territory: {qy.name(t)}. Plan and specialty splits are not run yet."  # contribution decomposition is Phase B
    return {
        "id": story_id(s), "kind": s["kind"], "title": qy.name(t) if s["kind"] == "territory" else f"{qy.name(t)}, plan {s['plan']}",
        "rank": rank, "proposed": proposed, "what_moved": moved,
        "decision": why + " " + (INVESTIGATE_ACTION if proposed == "investigate" else
                                 f"Over the story cap of this brief; code leaves it for the next one."),
        "population": _population(p), "granularity": grain, "time": _time(p),
    }


def build_plan(reg, f: Front) -> dict:
    """The triage plan for P1 (data-model.md TriagePlan), rendered, with this run's claims and evidence."""
    p = f.p
    cards: list[dict] = []
    if not p.calendar:
        for i, s in enumerate(f.found):
            cards.append(_card(reg, f, s, len(cards) + 1, "investigate" if i < MAX_STORIES else "over_cap"))
        if stages.competitor_status(reg, p) is not None:
            cards.append(_card(reg, f, None, len(cards) + 1, "investigate"))
    texts = [c[k] for c in cards for k in ("what_moved", "decision", "population", "granularity", "time")]
    bad = digits_outside_tokens("\n".join(texts))
    if bad:
        raise AssertionError(f"digit outside a claim token on a triage card: {bad[:3]}")
    withheld = [t for t in p.terrs if t not in p.ok]
    dropped = [{"territory": qy.name(t), "reason": "Within its normal range (code screen).", "layer": "code"} for t in f.quiet]
    for t in withheld:
        reasons = sorted({r for (w, tt), (h, rs) in p.status.items() if tt == t and h != "PASS" for r in (rs or "").split(";") if r})
        words = ", ".join(qy.REASONS.get(r, r.lower()) for r in reasons) or "failed checks"
        dropped.append({"territory": qy.name(t), "reason": f"Withheld at the feed gate ({words}). It cannot be investigated.",
                        "layer": "code"})
    state = "CALENDAR" if p.calendar else ("TRIAGE_REVIEW" if cards else "ROUTINE")
    proposed_ids = [c["id"] for c in cards if c["proposed"] == "investigate"]
    plan_id = "t-" + hashlib.sha256("|".join([p.question, reg.data_version, *proposed_ids]).encode()).hexdigest()[:12]
    for c in cards:
        for k in ("what_moved", "decision", "population", "granularity", "time"):
            c[k] = reg.render(c[k])
    return {
        "plan_id": plan_id, "question": p.question, "data_version": reg.data_version, "state": state,
        "weeks": list(p.weeks), "baseline": list(p.baseline), "focus": p.focus,
        "context": reg.render("\n".join(x for x in f.out if x)),  # stages 1 to 3 as the brief will state them
        "stories": cards, "dropped": dropped, "withheld": withheld, "candidates": len(f.found),
        "claims": reg.claims, "evidence": reg.evidence,
    }


def triage_record(plan: dict, order: list[str]) -> dict:
    """Who made each triage call (brief-002 FR-002): code proposed, dropped or capped; P1 kept, dropped or moved."""
    proposed = [c["id"] for c in plan["stories"] if c["proposed"] == "investigate"]
    calls = []
    for c in plan["stories"]:
        if c["proposed"] == "over_cap":
            calls.append({"story": c["id"], "title": c["title"], "outcome": "over_cap", "layer": "code"})
        elif c["id"] not in order:
            calls.append({"story": c["id"], "title": c["title"], "outcome": "dropped", "layer": "human"})
        else:
            moved = [s for s in proposed if s in order].index(c["id"]) != order.index(c["id"])
            calls.append({"story": c["id"], "title": c["title"], "outcome": "moved" if moved else "investigated",
                          "layer": "human" if moved else "code", "position": order.index(c["id"]) + 1})
    for d in plan["dropped"]:
        calls.append({"story": d["territory"], "title": d["territory"],
                      "outcome": "withheld" if d["reason"].startswith("Withheld") else "quiet", "layer": "code"})
    return {"plan_id": plan["plan_id"], "default": order == proposed, "order": list(order), "calls": calls,
            "reviewed_by": "Commercial Analyst (plan review)"}


def stage_flow(plan: dict, record: dict | None, verified: bool) -> list[dict]:
    """The seven stages with run states and actors (brief-002 FR-024; Briefing Architecture §6, §9)."""
    code = lambda name: {"kind": "code", "name": name}  # noqa: E731
    human = lambda name: {"kind": "human", "name": name}  # noqa: E731
    withheld = plan["withheld"]
    stage4_states, stage4_actors, stage4_note = [], [], "Skipped: no candidate story."
    if plan["state"] == "CALENDAR":
        stage3 = (["ROUTINE"], "Calendar week: lower volume is expected, so no story is opened.")
    elif plan["state"] == "ROUTINE":
        stage3 = (["ROUTINE"], "No material change.")
    else:
        stage3 = (["INVESTIGATION_REQUESTED"], "Candidate stories: " + ", ".join(c["title"] for c in plan["stories"]) + ".")
        stage4_states = ["TRIAGE_REVIEW", "INVESTIGATING", "EVIDENCE_RECEIVED"]
        stage4_actors = [code("triage rules (screen, caps, withheld cuts, continuing stories)"),
                         human("Commercial Analyst (plan review)"),
                         code("fixed order of checks (manager off)")]
        kept = [c["title"] for c in record["calls"] if c["outcome"] in ("investigated", "moved")] if record else []
        stage4_note = ("Investigated, in this order: " + (", ".join(kept) or "none") + "."
                       + ("" if not record or record["default"] else " The analyst changed the code plan."))
    return [
        {"stage": 1, "name": "Load and pin", "actors": [code("loader")], "states": ["LOADED"],
         "note": f"Data version {plan['data_version']}."},
        {"stage": 2, "name": "Validation gate", "actors": [code("feed-health gate")],
         "states": ["VALIDATION_WARNING" if withheld else "VALIDATED"],
         "note": ("Withheld: " + _names(withheld) + ".") if withheld else "Every cut passes."},
        {"stage": 3, "name": "Competitive intelligence", "actors": [code("governed KPIs and screen")],
         "states": stage3[0], "note": stage3[1]},
        {"stage": 4, "name": "Triage and investigation", "actors": stage4_actors, "states": stage4_states, "note": stage4_note},
        {"stage": 5, "name": "Narrative", "actors": [code("brief template (claim tokens)")], "states": ["DRAFTED"],
         "note": "Scripted template; agent builds use the constrained writer."},
        {"stage": 6, "name": "Verification", "actors": [code("number and wording checks")],
         "states": ["VERIFIED" if verified else "VERIFICATION_FLAGGED"], "note": "No digit outside a claim token."},
        {"stage": 7, "name": "Review and publish", "actors": [human("Commercial Analyst (approval)")],
         "states": ["IN_REVIEW"], "note": "The Brand Director sees it only after approval."},
    ]
