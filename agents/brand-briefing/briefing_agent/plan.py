"""The manager's triage (brief-002 FR-004, FR-005; A1): code proposes, the manager reorders or drops and sets
hypothesis order, code checks every call against the code plan. Never adds a story."""
from __future__ import annotations

import copy
import json
import re

from pharmagentics.tools.checks import DRIVERS

DEFAULT_HYPOTHESES = ["data", "access", "promotion", "supply", "competitor"]  # the scripted engine's fixed order
COMPETITOR = "competitor:BXE"
# The question leaves competitors out ("ignore Metacora", "without the competitor story", "skip competitors").
_EXCLUDES = re.compile(r"\b(ignore|ignoring|exclude|excluding|skip|skipping|without|leave out|leaving out|not about)\b"
                       r"[^.?!]*\b(competitors?|competition|metacora)\b", re.I)


def excludes_competitor(question: str) -> bool:
    """True when the question itself asks to leave competitors out (the text after the code-written prefix)."""
    return bool(_EXCLUDES.search(question.split(":", 1)[-1]))


def cards_text(plan: dict) -> str:
    lines = []
    for c in plan["stories"]:
        if c["proposed"] != "investigate":
            continue
        lines.append(f"- {c['id']}: {c['title']}. {c['what_moved']} Why code flagged it: {c['decision'].split(' Investigate:')[0]}")
    return "\n".join(lines) or "(none)"


def parse(reply: str) -> dict:
    """The JSON object in the model's reply (it may wrap it in prose or a code fence)."""
    m = re.search(r"\{.*\}", reply or "", re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    return json.loads(m.group(0))


def _match(name: str, proposed: list[str]) -> str:
    """The proposed id a loosely written name means ('metacora:BXE', 'PACIFIC', 'Mid-Atlantic'), else the name."""
    n = name.strip()
    if n in proposed:
        return n
    key = n.lower().split(":", 1)[-1].replace(" ", "_").replace("-", "_")
    for p in proposed:
        tail = p.lower().split(":", 1)[-1]
        if key == tail or (p == "competitor:BXE" and "metacora" in n.lower()):
            return p
    return n


def apply(code_plan: dict, reply: str, question: str = "") -> dict:
    """The plan P1 reviews: the code plan plus the manager's calls, checked by code. Invalid output falls back
    to the code plan and says so (a defined exit, never a crash)."""
    plan = copy.deepcopy(code_plan)
    proposed = [c["id"] for c in plan["stories"] if c["proposed"] == "investigate"]
    flags, problems, corrections = [], [], []
    try:
        out = parse(reply)
        known = lambda s: _match(s, proposed)  # noqa: E731
        raw_order = [s for s in out.get("order", []) if isinstance(s, str)]
        # A driver name in "order" is a known small-model slip (drivers belong in "hypotheses"): ignore it quietly.
        slips = [s for s in raw_order if s.strip().lower() in DRIVERS]
        order = [known(s) for s in raw_order if s not in slips]
        drop = {known(k): str(v)[:200] for k, v in (out.get("drop") or {}).items() if k.strip().lower() not in DRIVERS}
        hyps = {known(k): v for k, v in (out.get("hypotheses") or {}).items() if isinstance(v, list)}
        conf = str(out.get("confidence", "high")).lower()
        note = str(out.get("note", ""))[:300]
        foreign = sorted({s for s in [*order, *drop] if s not in proposed})
        if foreign:
            problems.append(f"named stories code did not propose: {', '.join(foreign)}")
        # A story both ordered and dropped is kept: "order" is the plan; contradictions never lose a story.
        drop = {k: v for k, v in drop.items() if k not in order}
        # A continuing story (Metacora) is not the manager's to drop: it stays unless the question leaves
        # competitors out. A small model drops it too readily, even when asked "is anything else going on?".
        if COMPETITOR in drop and COMPETITOR in proposed and not excludes_competitor(question):
            drop.pop(COMPETITOR)
            order.append(COMPETITOR)
            corrections.append("Code kept the Metacora story: a continuing story stays in the brief unless the question "
                               "leaves competitors out.")
        order = [s for s in dict.fromkeys(order) if s in proposed and s not in drop]
        # A proposed story the manager neither ordered nor dropped keeps code's position after the ordered ones.
        order += [s for s in proposed if s not in order and s not in drop]
        drop = {k: v for k, v in drop.items() if k in proposed}
    except (ValueError, json.JSONDecodeError, AttributeError) as exc:
        problems.append(f"unreadable plan ({exc})")
        order, drop, hyps, conf, note = list(proposed), {}, {}, "low", ""
    for c in plan["stories"]:
        if c["proposed"] != "investigate":
            c["manager"] = {"keep": False, "position": None, "why": "over the story cap (code)", "hypotheses": []}
            continue
        h = [d for d in (hyps.get(c["id"]) or []) if d in DRIVERS] if c["kind"] != "competitor" else []
        if c["kind"] != "competitor":
            h = list(dict.fromkeys(h + [d for d in DEFAULT_HYPOTHESES if d not in h]))  # every driver keeps a verdict
        c["manager"] = {"keep": c["id"] in order, "position": order.index(c["id"]) + 1 if c["id"] in order else None,
                        "why": drop.get(c["id"]), "hypotheses": h}
    if order != proposed:
        flags.append("The manager changed code's plan.")
    if conf == "low":
        flags.append("The manager marked its plan low-confidence.")
    if problems:
        flags.append("Code corrected the manager's plan: " + "; ".join(problems) + ".")
    plan.update(engine="agent", manager_order=order, manager_drop=drop, manager_note=note,
                manager_confidence="low" if conf == "low" else "high", flagged=bool(flags), flags=flags,
                corrections=corrections)
    return plan


def record(plan: dict, final: list[str], reviewed: bool) -> dict:
    """Who made each triage call: code, the manager (agent) or P1 (human)."""
    proposed = [c["id"] for c in plan["stories"] if c["proposed"] == "investigate"]
    manager = plan.get("manager_order", proposed)
    calls = []
    for c in plan["stories"]:
        if c["proposed"] == "over_cap":
            calls.append({"story": c["id"], "title": c["title"], "outcome": "over_cap", "layer": "code"})
            continue
        by_manager = c["id"] not in manager
        if c["id"] not in final:
            layer = "agent" if by_manager else "human"
            calls.append({"story": c["id"], "title": c["title"], "outcome": "dropped", "layer": layer,
                          "why": plan.get("manager_drop", {}).get(c["id"]) if by_manager else None})
            continue
        if by_manager:  # the manager dropped it, P1 put it back
            calls.append({"story": c["id"], "title": c["title"], "outcome": "restored", "layer": "human",
                          "position": final.index(c["id"]) + 1})
            continue
        kept_code = [s for s in proposed if s in final]
        kept_manager = [s for s in manager if s in final]
        if final.index(c["id"]) != kept_manager.index(c["id"]):
            layer, outcome = "human", "moved"
        elif kept_manager.index(c["id"]) != kept_code.index(c["id"]):
            layer, outcome = "agent", "moved"
        else:
            layer, outcome = "code", "investigated"
        calls.append({"story": c["id"], "title": c["title"], "outcome": outcome, "layer": layer,
                      "position": final.index(c["id"]) + 1})
    for d in plan["dropped"]:
        calls.append({"story": d["territory"], "title": d["territory"],
                      "outcome": "withheld" if d["reason"].startswith("Withheld") else "quiet", "layer": "code"})
    return {"plan_id": plan["plan_id"], "default": final == proposed, "order": list(final), "calls": calls,
            "manager_order": manager, "flagged": plan.get("flagged", False), "flags": plan.get("flags", []),
            "reviewed_by_person": reviewed, "would_pause": plan.get("flagged", False) and not reviewed}
