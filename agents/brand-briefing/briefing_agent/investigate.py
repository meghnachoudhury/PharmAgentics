"""Stage 4 for build 3: one MCP session per run, a bounded Magentic team per approved story (brief-002
FR-006 to FR-017). Depth two; the no-repeat ledger is on; code closes any story the team left open."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

from agent_framework import Agent, MCPStdioTool
from agent_framework.orchestrations import MagenticBuilder
from mcp.client.stdio import StdioServerParameters

from pharmagentics.llm import REPO_ROOT, chat_client, chat_options
from pharmagentics.mcp_server import AGENT_TOOLS
from pharmagentics.tracing import finish, span

from briefing_lowcode.team import RunLog, _call, _model_failure  # build 2's middleware and helpers

HERE = Path(__file__).resolve().parent
ORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def server() -> StdioServerParameters:
    """The MCP server on stdio with build 3's no-repeat ledger on."""
    env = {**{k: v for k, v in os.environ.items() if k in ("SYSTEMROOT", "PATH")},
           "PYTHONPATH": str(REPO_ROOT / "src"), "PHARMAGENTICS_MCP_NO_REPEAT": "1"}
    return StdioServerParameters(command=sys.executable, args=["-m", "pharmagentics.mcp_server"], env=env, cwd=str(REPO_ROOT))


def _read(rel: str) -> str:
    return (HERE / rel).read_text(encoding="utf-8")


def wall_scale() -> float:
    """The wall-clock caps in agent.yaml are tuned for a GPU. A CPU host sets PHARMAGENTICS_AGENT_WALL_SCALE to
    stretch them, so slow is not mistaken for stuck (a capped story would close with drivers untested)."""
    try:
        return max(1.0, float(os.environ.get("PHARMAGENTICS_AGENT_WALL_SCALE", "1")))
    except ValueError:
        return 1.0


def story_task(card: dict, hypotheses: list[str]) -> str:
    t = card["territory"]
    order = ", ".join(hypotheses)
    return (f"Investigate one story for the weekly BXA brief.\nStory: {card['title']} (territory ID {t}).\n"
            f"Plan's hypothesis order: {order}.\n"
            f"Data Forensics first: check_data({t}). Then the Driver Investigator tests the other drivers in that "
            f"order with check_access, check_promotion, check_supply or check_competitor on {t}, one call each, "
            f"and closes the story with story_confidence({t}). Stop once story_confidence has closed it.")


async def _team(cfg: dict, spec: str, mcp, task: str, log: RunLog, wall: float) -> str | None:
    """Run one story's team; return why it stopped early, or None."""
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
        manager = Agent(client=chat, name="manager", instructions=_read(cfg["prompts"]["manager"]),
                        default_options=opts, middleware=[log.chat("manager")])
        workflow = MagenticBuilder(participants=participants, manager_agent=manager,
                                   final_answer_prompt=_read(cfg["prompts"]["story_done"]), **cfg["caps"]).build()
        try:
            await asyncio.wait_for(workflow.run(task), timeout=wall)
            return None
        except asyncio.TimeoutError:
            return "wall_clock"
        except Exception as exc:  # a failed model request is a defined exit; anything else is a run error
            if not _model_failure(exc):
                raise
            return "model_error"


async def investigate(cfg: dict, spec: str, mcp, plan: dict, order: list[str], log: RunLog) -> tuple[list[dict], list[dict]]:
    """Each approved story in P1's (or the manager's) order. Returns the story sections and per-story notes."""
    by_id = {c["id"]: c for c in plan["stories"]}
    started, stories, notes, n = time.time(), [], [], 0
    scale = wall_scale()
    for sid in order:
        card = by_id[sid]
        if card["kind"] == "competitor":
            text = await _call(mcp, "competitor_section", lead=f"Story {ORD[n + 1]}: competitor Metacora")
            if text:
                n += 1
                stories.append({"id": sid, "n": n, "section": text})
            continue
        n += 1
        left = cfg["run_wall_seconds"] * scale - (time.time() - started)
        capped = "run_cap" if left < 20 else None
        with span(f"story_{n}_{card['territory']}", inputs={"story": sid, "hypotheses": card["manager"]["hypotheses"]}) as sp:
            if not capped:
                capped = await _team(cfg, spec, mcp, story_task(card, card["manager"]["hypotheses"]), log,
                                     min(cfg["story_wall_seconds"] * scale, left))
            section = await _call(mcp, "story_section", territory=card["territory"], n=n)  # code closes the story
            finish(sp, {"capped": capped, "section": section})
        stories.append({"id": sid, "n": n, "section": section})
        notes.append({"story": sid, "capped": capped})
    return stories, notes
