"""Follow-ups answered by the agent on Claude Haiku (brief-006 slice 4; Session 2026-11-20).

One agent with both specialist tool sets over a fresh MCP session pinned to the brief's scope. It sees the brief's
sections with their numbers masked, so any number it states must come from a tool it calls in this turn (a claim
token). Code guards run first and need no model: out of scope, no driver for a projected or estimated cut,
no individual rep, no such section (tools/followup.py). Its reply goes through the same checks as the writer:
no digit outside a token, no token no tool produced; one revision; what still fails is not shown. The turn
stops at 60 seconds and then says so; nothing is guessed (FR-010).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import AsyncExitStack

from agent_framework import Agent, MCPStdioTool
from mcp.client.client import Client

from pharmagentics.llm import chat_client, chat_options
from pharmagentics.mcp_server import AGENT_TOOLS
from pharmagentics.tools import followup as rules
from pharmagentics.tools.queries import name
from pharmagentics.tools.registry import cite, digits_outside_tokens

from briefing_lowcode.team import RunLog, _call

from .investigate import server

LIMIT_SECONDS = 60
GUARDS = ("out_of_scope", "no_driver", "no_individual", "no_section")
SECTION = re.compile(r"§\s*(\d+(?:\.\d+)?)")
NUMBER = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?%?")
TOKEN = re.compile(r"\{c(\d+)\}")
TIMED_OUT = "Didn't finish in time; nothing was guessed."
PROMPT = """You answer one follow-up question about a weekly brand-performance brief for the fictional brand BXA
(synthetic data). The brief's sections are below with every number masked as [n]: you cannot copy them.

Rules:
- Every number you write must be a claim token such as {{c4}} copied exactly from a tool result in this turn. Never
  write a digit yourself. Dates such as 2026-06-08 may stay. Call the tools you need, then answer.
- Cite the section you answer about as "§3.1" (only sections listed below).
- For a split by plan, specialty or channel, call split_change. Never generalize from a cut marked noisy.
- The brief's sections are final: a check you rerun now confirms or adds detail; it does not reopen a story.
- One to four short sentences. Use only what the tools and sections say. Causal words only for a High story.
- Never name or number an individual rep. Say "competitive intelligence", never "surveillance". "New patients" only
  for NBRx. Never name a driver for a territory the brief marks as projected or estimated.

The brief ({scope}):
{sections}

The analyst asks{about}: {question}"""


def _masked(sections: list[dict]) -> str:
    def mask(text: str) -> str:
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
        text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "\0", text)
        text = NUMBER.sub("[n]", text)
        for d in dates:
            text = text.replace("\0", d, 1)
        return text
    return "\n".join(f"§{s['number']} {s['title']}\n{mask(s.get('text') or '')}" for s in sections)


def _problems(reply: str, n_claims: int) -> list[str]:
    out = []
    if (bad := digits_outside_tokens(SECTION.sub(" ", reply))):
        out.append(f"typed numbers {', '.join(bad[:5])}; use claim tokens from the tool results")
    invented = sorted({m.group(0) for m in TOKEN.finditer(reply) if not 0 < int(m.group(1)) <= n_claims})
    if invented:
        out.append(f"tokens no tool produced {', '.join(invented)}")
    if re.search(r"surveillance", reply, re.I):
        out.append('says "surveillance"')
    return out


def _scope_question(brief: dict, question: str) -> str:
    t = brief.get("territory_id") or "NATIONAL"
    where = "" if t == "NATIONAL" else f" in {name(t)}"
    return f"Week of {brief.get('week_start')}{where}: {question}"


async def _agent_turn(brief: dict, question: str, section: str | None, spec: str, log: RunLog) -> dict:
    sections = brief.get("sections") or []
    have = {s["number"] for s in sections}
    base = server()
    params = base.model_copy(update={"env": {**(base.env or {}), "PHARMAGENTICS_MCP_FOLLOW_UP": "1"}})  # no story-so-far status
    async with Client(params) as mcp, AsyncExitStack() as stack:
        await _call(mcp, "open_run", question=_scope_question(brief, question))
        tools = MCPStdioTool(name="pharmagentics_follow_up", mcp_client=mcp, load_prompts=False,
                             allowed_tools=AGENT_TOOLS["data_forensics"] + AGENT_TOOLS["driver_investigator"]
                             + AGENT_TOOLS["follow_up"])
        await stack.enter_async_context(tools)
        agent = Agent(client=chat_client(spec), name="follow_up", tools=tools, default_options=chat_options(spec),
                      instructions="Answer with claim tokens only; never type a digit.", middleware=log.for_agent("follow_up"))
        about = f" about §{section}" if section else ""
        scope = f"BXA, {name(brief.get('territory_id') or 'NATIONAL')}, week of {brief.get('week_start')}"
        prompt = PROMPT.format(scope=scope, sections=_masked(sections), about=about, question=question)
        reply = (await agent.run(prompt)).text or ""
        run = json.loads(await _call(mcp, "export_run"))
        revised = False
        if (bad := _problems(reply, len(run["claims"]))):
            revised = True
            reply = (await agent.run("Rewrite your answer to fix: " + "; ".join(bad)
                                     + ". Keep every number as a claim token from the tool results.")).text or ""
            run = json.loads(await _call(mcp, "export_run"))
    claims, evidence = run["claims"], run["evidence"]
    if _problems(reply, len(claims)):
        return {"answer": "I could not answer with traced numbers, so nothing is shown. Ask the question another way.",
                "claims": [], "evidence": [], "cited": [section] if section in have else [], "kind": "agent_dropped",
                "revised": revised}
    used = list(dict.fromkeys(int(m.group(1)) for m in TOKEN.finditer(reply) if 0 < int(m.group(1)) <= len(claims)))
    text, _ = cite(reply, claims, index={n: i for i, n in enumerate(used)})
    kept = [claims[n - 1] for n in used]
    # Follow-up evidence ids are prefixed so they never collide with the brief's (both sit in one thread).
    ids = {c["evidence_id"] for c in kept}
    rename = {eid: f"f{eid}" for eid in ids}
    cited = sorted({*(m for m in SECTION.findall(text) if m in have), *([section] if section in have else [])})
    return {"answer": text, "cited": cited, "kind": "agent", "revised": revised,
            "claims": [dict(c, evidence_id=rename[c["evidence_id"]]) for c in kept],
            "evidence": [dict(e, id=rename[e["id"]]) for e in evidence if e["id"] in ids]}


def answer(brief: dict, question: str, section: str | None, model: str) -> dict:
    """One agent turn on a stored brief (its sections, claims, evidence and scope)."""
    started = time.perf_counter()
    guard = rules.answer(brief, question, section)
    if guard["kind"] in GUARDS:  # code decides these, with no model (FR-007; brief-003 FR-023; B-VI)
        return {**guard, "engine": "agent", "seconds": round(time.perf_counter() - started, 3),
                "trajectory": {"llm_calls": 0, "guard": guard["kind"]}}
    log = RunLog()
    about = section or (m.group(1) if (m := SECTION.search(question or "")) else None)
    try:
        turn = asyncio.run(asyncio.wait_for(_agent_turn(brief, question, about, model, log), timeout=LIMIT_SECONDS))
    except asyncio.TimeoutError:
        turn = {"answer": TIMED_OUT, "claims": [], "evidence": [], "cited": [], "kind": "timeout", "error": "timeout"}
    return {**turn, "engine": "agent", "offer": None, "seconds": round(time.perf_counter() - started, 3),
            "trajectory": {"llm_calls": log.llm_calls, "tools": log.tools, "tokens": log.tokens, "model": model}}
