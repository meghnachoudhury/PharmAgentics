"""Briefing build 3: the Briefing agent (Briefing Architecture §14; brief-002 Phase B).

    scope gate (code) -> code triage (Phase A) -> manager's plan (agent; A1) -> P1 by exception (always in UAT)
    -> per-story Magentic team: manager, Data Forensics, Driver Investigator (MCP tools, no-repeat ledger)
    -> code-built brief sections + writer's answer and story sentences (LLM) -> verification, one revision

Entry points: `answer(question)` for the eval harness (no person: the manager's plan runs and the record
says whether it would have paused); `triage(question)` and `run_with_plan(question, decision, plan)` for
the UAT worker. Agent code never imports eval/.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

import yaml
from agent_framework import Agent
from mcp.client.client import Client

from pharmagentics.llm import chat_client, chat_options, model_spec
from pharmagentics.tools.registry import digits_outside_tokens
from pharmagentics.tracing import finish, span

from briefing_baseline import pipeline as scripted
from briefing_baseline.triage import stage_flow
from briefing_lowcode.team import RunLog, _call

from . import plan as planmod
from . import write
from .investigate import investigate, server
from .scope import out_of_scope

HERE = Path(__file__).resolve().parent
NAME = "briefing_agent"


def load_config() -> dict:
    return yaml.safe_load((HERE / "agent.yaml").read_text(encoding="utf-8"))


def config_version() -> str:
    h = hashlib.sha256()
    for f in [HERE / "agent.yaml", *sorted((HERE / "prompts").glob("*.md"))]:
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:12]


def answer(question: str, model: str | None = None) -> dict:
    """Eval entry point: question in, AnswerEnvelope dict out."""
    return asyncio.run(_answer(question, model))


def triage(question: str, model: str | None = None) -> dict:
    """UAT: the plan P1 reviews (code plan plus the manager's calls)."""
    cfg = load_config()
    return asyncio.run(_triage(question, model_spec(model or cfg.get("model")), RunLog()))


def run_with_plan(question: str, decision: dict, plan: dict, model: str | None = None) -> dict:
    """UAT: the brief on P1's decision over the reviewed plan. Returns envelope, triage record and flow."""
    cfg = load_config()
    if decision.get("plan_id") != plan.get("plan_id"):
        raise scripted.StalePlan("The decision is for another plan.")
    allowed = [c["id"] for c in plan["stories"] if c["proposed"] == "investigate"]
    order = list(decision.get("stories", []))
    if any(s not in allowed for s in order) or len(set(order)) != len(order):
        raise ValueError(f"Not a story this plan proposes: {', '.join(s for s in order if s not in allowed)}")
    return asyncio.run(_run(question, plan, order, model_spec(model or cfg.get("model")), reviewed=True, log=RunLog()))


async def _ask(spec: str, prompt: str, log: RunLog, name: str) -> str:
    agent = Agent(client=chat_client(spec), name=name, default_options=chat_options(spec), middleware=[log.chat(name)])
    return (await agent.run(prompt)).text or ""


async def _triage(question: str, spec: str, log: RunLog) -> dict:
    cfg = load_config()
    code_plan = scripted.triage(question)  # ValueError outside the release
    scope = out_of_scope(question)
    if scope:
        return dict(code_plan, engine="agent", state="OUT_OF_SCOPE", scope=scope, stories=[], flagged=False, flags=[],
                    manager_order=[], manager_drop={}, manager_note="", model=spec)
    if code_plan["state"] != "TRIAGE_REVIEW":
        return dict(planmod.apply(code_plan, '{"order": []}', question), model=spec)
    prompt = (HERE / cfg["prompts"]["manager_triage"]).read_text(encoding="utf-8").format(
        question=question.split(":", 1)[-1].strip(), cards=planmod.cards_text(code_plan))
    with span("4_triage_manager", inputs={"cards": planmod.cards_text(code_plan)}) as sp:
        reply = await _ask(spec, prompt, log, "manager_triage")
        plan = planmod.apply(code_plan, reply, question)
        finish(sp, {"reply": reply, "order": plan["manager_order"], "flags": plan["flags"]})
    return dict(plan, model=spec)


def _left_out(plan: dict, order: list[str]) -> list[str]:
    proposed = [c for c in plan["stories"] if c["proposed"] == "investigate"]
    manager = plan.get("manager_order", [c["id"] for c in proposed])
    by_manager, by_analyst = [], []
    for c in proposed:
        if c["id"] in order:
            continue
        if c["id"] not in manager:
            why = (plan.get("manager_drop") or {}).get(c["id"]) or ""
            reason = why.rstrip(".") if why and not digits_outside_tokens(why) and "{c" not in why else ""
            by_manager.append(c["title"] + (f", because: {reason[0].lower()}{reason[1:]}" if reason else ""))
        else:
            by_analyst.append(c["title"])
    return ([f"Left out of this brief by the manager: {'; '.join(by_manager)}."] if by_manager else []) + \
           ([f"Left out of this brief by the analyst: {', '.join(by_analyst)}."] if by_analyst else [])


async def _write(cfg: dict, spec: str, question: str, sections: dict, stories: list[dict], claims: list[dict],
                 evidence: list[dict], log: RunLog) -> tuple[str, dict, bool, list[str]]:
    n_claims = len(claims)
    story_tokens = {s["id"]: write.tokens(s["section"]) for s in stories}
    story_tokens["_sections"] = write.tokens("\n".join(sections["header"] + sections["data_health"] + sections["kpis"]))
    shown = write.sections_text(sections, stories)
    gloss_text, glosses = write.glossary(shown, claims, evidence)  # what each number measures, written by code
    prompt = (HERE / cfg["prompts"]["writer"]).read_text(encoding="utf-8").format(
        question=question.split(":", 1)[-1].strip(), sections=shown, glossary=gloss_text or "(no numbers)")
    with span("5_writer") as sp:
        raw = await _ask(spec, prompt, log, "writer")
        try:
            reply = planmod.parse(raw)
        except Exception:  # noqa: BLE001 - an unreadable reply means no LLM sentences, never a crash
            reply = {}
        finish(sp, {"reply": raw})
    revised = False
    with span("6_verification") as sp:
        bad = write.check(reply, story_tokens, n_claims, glosses)
        if bad:
            allowed = "\n".join(f"- {k}: {', '.join(sorted(v)) or '(none)'}" for k, v in story_tokens.items() if k != "_sections")
            allowed += "\n- answer: any token above, or " + (", ".join(sorted(story_tokens["_sections"])) or "(none)")
            fix = (HERE / cfg["prompts"]["revise"]).read_text(encoding="utf-8").format(
                problems="\n".join(f"- {k}: {'; '.join(v)}" for k, v in bad.items()), allowed=allowed,
                glossary=gloss_text or "(no numbers)", reply=json.dumps(reply))
            raw2 = await _ask(spec, fix, log, "reviser")
            try:
                reply = planmod.parse(raw2)
            except Exception:  # noqa: BLE001
                pass
            revised = True
        answer_text, sentences, dropped = write.clean(reply, story_tokens, n_claims, glosses)
        finish(sp, {"problems": bad, "revised": revised, "dropped": dropped})
    return answer_text, sentences, revised, dropped


async def _run(question: str, plan: dict, order: list[str], spec: str, reviewed: bool, log: RunLog) -> dict:
    cfg = load_config()
    started = time.time()
    if plan.get("state") == "OUT_OF_SCOPE":
        env = scripted.answer(question)
        env.update(system=f"{NAME}:{spec}", answer=plan["scope"] + "\n" + env["answer"],
                   trajectory={"scope": "out", "tools": [], "llm_calls": 0, "capped": None, "model": spec,
                               "config_version": config_version(), "seconds": round(time.time() - started, 1)})
        return {"envelope": env, "triage": None, "flow": None}
    async with Client(server()) as mcp:
        with span("1_load_and_pin", inputs={"question": question}, model=spec, config_version=config_version()) as sp:
            pinned = await _call(mcp, "open_run", question=question)
            sections = json.loads(await _call(mcp, "brief_sections"))
            finish(sp, {"run_context": pinned})
        with span("4a_investigation", inputs={"order": order}) as sp:
            stories, notes = (await investigate(cfg, spec, mcp, plan, order, log)) if plan["state"] == "TRIAGE_REVIEW" else ([], [])
            finish(sp, {"notes": notes, "tool_sequence": log.tools})
        dropped_line = await _call(mcp, "dropped_line")
        run = json.loads(await _call(mcp, "export_run"))
    claims = run["claims"]
    answer_text, sentences, revised, dropped = await _write(cfg, spec, question, sections, stories, claims,
                                                            run["evidence"], log)
    template = write.assemble(sections, stories, answer_text, sentences, _left_out(plan, order), dropped_line)
    if (bad := digits_outside_tokens(template)):  # code sections are clean; this guards the assembly itself
        raise AssertionError(f"digit outside a claim token: {bad[:3]}")
    text, used, citations = write.render(template, claims)
    keep = {c["evidence_id"] for c in used}
    record = planmod.record(plan, order, reviewed)
    flow_record = dict(record, calls=[dict(c, outcome="investigated") if c["outcome"] == "restored" else c for c in record["calls"]])
    flow = write.flow(stage_flow(plan, flow_record, verified=True), plan, record, log.tools, revised, spec)
    capped = next((n["capped"] for n in notes if n["capped"]), None)
    envelope = {
        "system": f"{NAME}:{spec}", "answer": text, "claims": used,
        "evidence": [e for e in run["evidence"] if e["id"] in keep],
        "abstained": bool(run["abstained"]), "citations": citations,
        "trajectory": {"tools": log.tools, "llm_calls": log.llm_calls, "tokens": log.tokens, "capped": capped,
                       "revised": revised, "dropped_pieces": dropped, "stories": run["stories"], "notes": notes,
                       "manager_order": plan.get("manager_order"), "flagged": plan.get("flagged"),
                       "would_pause": record["would_pause"], "seconds": round(time.time() - started, 1),
                       "config_version": config_version(), "model": spec},
    }
    return {"envelope": envelope, "triage": record, "flow": flow}


async def _answer(question: str, model: str | None) -> dict:
    cfg = load_config()
    spec = model_spec(model or cfg.get("model"))
    log = RunLog()
    try:
        plan = await _triage(question, spec, log)
    except ValueError:  # outside the release: the scripted engine says so, with no model
        return dict(scripted.answer(question), system=f"{NAME}:{spec}")
    result = await _run(question, plan, plan.get("manager_order", []), spec, reviewed=False, log=log)
    return result["envelope"]
