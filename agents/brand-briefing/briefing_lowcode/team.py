"""Briefing low-code build: Magentic-One (Microsoft Agent Framework) over the PharmAgentics MCP server.

team.yaml and prompts/ configure the team. This module only wires them to the framework and keeps the
number rules, which are code in every build:

1 load and pin   the MCP server opens the run: period, baseline weeks and one data version
4a investigation the framework's manager plans and delegates; specialists call MCP tools (2, 3, 4a)
5 narrative      the manager's final answer, written in claim tokens
6 verification   digits outside tokens get one revision; then code fills tokens from the run's evidence

A capped run still ends with a brief (guardrail rule 4). The framework stops with no answer at its round
cap; code stops the team at the wall-clock cap or when a model request fails (a timeout, a dead runner).
Each time code asks the manager for the final answer from the specialists' reports and records why it stopped.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

import yaml
from agent_framework import Agent, AgentMiddleware, ChatMiddleware, FunctionMiddleware, MCPStdioTool, Message
from agent_framework.exceptions import ChatClientException
from agent_framework.orchestrations import MagenticBuilder
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

from pharmagentics.llm import REPO_ROOT, chat_client, chat_options, model_spec
from pharmagentics.mcp_server import AGENT_TOOLS
from pharmagentics.tools.registry import digits_outside_tokens
from pharmagentics.tracing import finish, span

HERE = Path(__file__).resolve().parent
NAME = "briefing_lowcode"
_TOKEN = re.compile(r"\{c(\d+)\}")
_CAPPED = "Workflow terminated due to reaching maximum"


def load_config() -> dict:
    cfg = yaml.safe_load((HERE / "team.yaml").read_text(encoding="utf-8"))
    return cfg


def _read(rel: str) -> str:
    return (HERE / rel).read_text(encoding="utf-8")


def config_version() -> str:
    """Hash of team.yaml and every prompt, so each run records which configuration produced it."""
    h = hashlib.sha256()
    for f in [HERE / "team.yaml", *sorted((HERE / "prompts").glob("*.md"))]:
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:12]


def answer(question: str, model: str | None = None) -> dict:
    """The harness entry point: question in, AnswerEnvelope dict out."""
    return asyncio.run(_answer(question, model))


class RunLog:
    """Middleware that records each agent turn, LLM call and tool call, and wraps each in a span."""

    def __init__(self):
        self.reports: list[tuple[str, str]] = []  # (agent, text) for every specialist turn
        self.tools: list[str] = []
        self.llm_calls = 0
        self.tokens = {"input": 0, "output": 0}

    def for_agent(self, name: str) -> list:
        log = self

        class _Agent(AgentMiddleware):
            async def process(self, context, call_next):
                ask = context.messages[-1].text if context.messages else ""
                with span(f"agent:{name}", "AGENT", inputs={"instruction": ask}) as sp:
                    await call_next()
                    text = getattr(context.result, "text", "") or ""
                    log.reports.append((name, text))
                    finish(sp, {"report": text})

        class _Tool(FunctionMiddleware):
            async def process(self, context, call_next):
                tool = context.function.name
                with span(f"tool:{tool}", "TOOL", inputs=dict(context.arguments or {}), agent=name) as sp:
                    await call_next()
                    log.tools.append(tool)
                    finish(sp, {"result": _text(context.result)})

        mws: list = [_Tool(), log.chat(name)]
        return [_Agent(), *mws]

    def chat(self, name: str) -> ChatMiddleware:
        log = self

        class _Chat(ChatMiddleware):
            async def process(self, context, call_next):
                last = context.messages[-1].text if context.messages else ""
                with span(f"llm:{name}", "CHAT_MODEL", inputs={"last_message": last[-4000:]}) as sp:
                    await call_next()
                    log.llm_calls += 1
                    usage = getattr(context.result, "usage_details", None) or {}
                    log.tokens["input"] += usage.get("input_token_count") or 0
                    log.tokens["output"] += usage.get("output_token_count") or 0
                    finish(sp, {"text": getattr(context.result, "text", "") or "", "usage": dict(usage)})

        return _Chat()


def _text(result) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "\n".join(_text(r) for r in result)
    return getattr(result, "text", None) or str(result)


def _server() -> StdioServerParameters:
    """The MCP server as a subprocess on stdio: one process, one run, one Registry."""
    env = {"PYTHONPATH": str(REPO_ROOT / "src")}
    return StdioServerParameters(command=sys.executable, args=["-m", "pharmagentics.mcp_server"], env=env, cwd=str(REPO_ROOT))


async def _call(mcp: Client, tool: str, **args) -> str:
    result = await mcp.call_tool(tool, args)
    return "\n".join(getattr(c, "text", "") for c in result.content)


def _task(question: str, pinned: str) -> str:
    return (f"Question from the brand team: {question}\n\n"
            f"Run context, pinned by code:\n{pinned}\n\n"
            "Answer the question with a short brief. Every number must come from a team member's tool "
            "results as a claim token such as {c7}; nobody types a number.")


def _output_text(outputs: list) -> str:
    if not outputs:
        return ""
    last = outputs[-1]
    if isinstance(last, list):
        last = last[-1] if last else ""
    return _text(last)


async def _answer(question: str, model: str | None, log: "RunLog | None" = None) -> dict:
    cfg = load_config()
    spec = model_spec(model or cfg.get("model"))
    log = log or RunLog()
    started = time.time()
    async with Client(_server()) as mcp:
        with span("1_load_and_pin", inputs={"question": question}, model=spec, config_version=config_version()) as sp:
            pinned = await _call(mcp, "open_run", question=question)
            finish(sp, {"run_context": pinned})
        capped = None  # else why the team stopped early: rounds, wall_clock, model_error, no_answer
        if pinned.startswith("That period is outside the release"):
            draft = pinned
        else:
            with span("4a_magentic_team", inputs={"task": _task(question, pinned)}) as sp:
                draft, capped = await _run_team(cfg, spec, mcp, _task(question, pinned), log)
                finish(sp, {"draft": draft, "capped": capped, "tool_sequence": log.tools})
        run = json.loads(await _call(mcp, "export_run"))

    claims = run["claims"]
    with span("6_verification") as sp:
        bad, invented = digits_outside_tokens(draft), _invented(draft, claims)
        revised = False
        if bad or invented:
            draft = await _revise(cfg, spec, draft, bad, invented, claims, log)
            revised = True
        # What is left stays visible in the brief, flagged for review (Briefing §5.6), and the scorers count it.
        still, still_invented = digits_outside_tokens(draft), _invented(draft, claims)
        finish(sp, {"digits_outside_tokens": bad, "invented_tokens": invented, "revised": revised,
                    "still_outside": still, "still_invented": still_invented})

    text = _TOKEN.sub(lambda m: claims[int(m.group(1)) - 1]["value"] if 0 < int(m.group(1)) <= len(claims) else m.group(0), draft)
    used = sorted({int(n) for n in _TOKEN.findall(draft)} & set(range(1, len(claims) + 1)))
    # The envelope keeps only the claims the answer uses, each linked to its evidence item.
    keep_claims = [claims[n - 1] for n in used]
    keep_ids = {c["evidence_id"] for c in keep_claims}
    return {
        "system": f"{NAME}:{spec}",
        "answer": text,
        "claims": keep_claims,
        "evidence": [e for e in run["evidence"] if e["id"] in keep_ids],
        "abstained": bool(run["abstained"]),
        "trajectory": {"tools": log.tools, "llm_calls": log.llm_calls, "tokens": log.tokens, "capped": capped,
                       "revised": revised, "digits_outside_tokens": still + still_invented,
                       "seconds": round(time.time() - started, 1),
                       "stories": run["stories"], "config_version": config_version(), "model": spec},
    }


async def _run_team(cfg: dict, spec: str, mcp: Client, task: str, log: RunLog) -> tuple[str, str | None]:
    chat, opts = chat_client(spec), chat_options(spec)
    async with AsyncExitStack() as stack:
        participants = []
        for p in cfg["participants"]:
            tool = MCPStdioTool(name=f"pharmagentics_{p['tools']}", mcp_client=mcp, allowed_tools=AGENT_TOOLS[p["tools"]],
                                load_prompts=False)
            await stack.enter_async_context(tool)
            participants.append(Agent(client=chat, name=p["name"], description=" ".join(p["description"].split()),
                                      instructions=_read(p["instructions"]), tools=tool, default_options=opts,
                                      middleware=log.for_agent(p["name"])))
        manager = Agent(client=chat, name="manager", instructions=_read(cfg["manager"]["instructions"]),
                        default_options=opts, middleware=[log.chat("manager")])
        final_prompt = _read(cfg["manager"]["final_answer_prompt"])
        workflow = MagenticBuilder(participants=participants, manager_agent=manager, final_answer_prompt=final_prompt,
                                   **cfg["caps"]).build()
        reason = None
        try:
            result = await asyncio.wait_for(workflow.run(task), timeout=cfg.get("wall_seconds"))
            draft = _output_text(result.get_outputs())
        except asyncio.TimeoutError:
            draft, reason = "", "wall_clock"
        except Exception as exc:  # only a failed model request is a defined exit; anything else is a run error
            if not _model_failure(exc):
                raise
            draft, reason = "", "model_error"
    if draft.startswith(_CAPPED):
        reason = "rounds"
    if reason or not draft.strip():
        reason = reason or "no_answer"
        return await _final_from_reports(cfg, spec, task, log, reason), reason
    return draft, None


def _model_failure(exc: BaseException) -> bool:
    """True when `exc` is, wraps or groups a failed model request."""
    seen, todo = set(), [exc]
    while todo:
        e = todo.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if isinstance(e, ChatClientException):
            return True
        todo += [e.__cause__, e.__context__, *getattr(e, "exceptions", ())]
    return False


def _invented(draft: str, claims: list[dict]) -> list[str]:
    """Tokens in the draft that no tool produced."""
    return sorted({m.group(0) for m in _TOKEN.finditer(draft) if not 0 < int(m.group(1)) <= len(claims)})


async def _final_from_reports(cfg: dict, spec: str, task: str, log: RunLog, reason: str) -> str:
    """Defined exit at a cap: the final answer from what the specialists reported, nothing else."""
    reports = "\n\n".join(f"[{who}]\n{text}" for who, text in log.reports if text.strip()) or "(no reports)"
    prompt = _read(cfg["manager"]["final_answer_prompt"]).format(task=task)
    why = {"rounds": "hit its round cap", "wall_clock": "hit its time cap", "model_error": "lost its model mid-run"}
    prompt += (f"\nThe team stopped early: it {why.get(reason, 'gave no final answer')}. Close any story without "
               "a confidence level as \"unresolved, investigate next\".\n\nTeam reports:\n" + reports)
    agent = Agent(client=chat_client(spec), name="manager", instructions=_read(cfg["manager"]["instructions"]),
                  default_options=chat_options(spec), middleware=[log.chat("manager_final")])
    return (await agent.run(prompt)).text


async def _revise(cfg: dict, spec: str, draft: str, bad: list[str], invented: list[str], claims: list[dict],
                  log: RunLog) -> str:
    """One revision (Briefing §5.6): stray digits become tokens, invented tokens go; a number with no token is dropped."""
    legend = "\n".join(f"{{c{i}}} = {c['value']}" for i, c in enumerate(claims, 1)) or "(none)"
    prompt = (_read(cfg["revision_prompt"]).replace("{bad}", ", ".join(bad[:20]) or "none")
              .replace("{invented}", ", ".join(invented) or "none").replace("{legend}", legend)
              .replace("{draft}", draft))
    agent = Agent(client=chat_client(spec), name="reviser", default_options=chat_options(spec),
                  middleware=[log.chat("reviser")])
    return (await agent.run(prompt)).text
