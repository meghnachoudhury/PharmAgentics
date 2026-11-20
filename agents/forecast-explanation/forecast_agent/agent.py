"""Stage 4 with a model: the investigator chooses comparisons and verdicts through tools bound to one Case.
Everything it can do is an engine operation, so a number never comes from the model. A step budget and a
wall-clock cap end every run; if the model fails, the rules policy decides whatever is still open."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Annotated

from agent_framework import Agent, tool

from pharmagentics.llm import chat_client, chat_options

from .engine import Case, Refused
from .policy import run_rules
from .scope import INTENTS

MAX_TOOL_CALLS = int(os.environ.get("FORECAST_AGENT_MAX_TOOL_CALLS", "16"))
WALL_SECONDS = float(os.environ.get("FORECAST_AGENT_WALL_SECONDS", "600"))
PROMPT = (os.path.dirname(__file__) + "/prompts/investigator.md")


def briefing(case: Case) -> str:
    """The investigator's opening context: scope, data checks, miss, territory screen, candidates."""
    var = case.variance()
    screen = [{k: r[k] for k in ("territory", "miss", "pct", "beyond_peers", "standout")} for r in case.screen()]
    return json.dumps({
        "question": case.scope.question, "intent": INTENTS[case.scope.intent], "territory": case.cut,
        "weeks": [case.weeks[0], case.weeks[-1]], "usable_weeks": len(case.usable),
        "set_aside_provisional_weeks": case.provisional,
        "miss": {"forecast_trx": round(var["forecast"] or 0), "actual_trx": round(var["actual"] or 0),
                 "miss_trx": round(var["variance"] or 0), "miss_pct_of_forecast": round(var["pct"] or 0, 1)},
        "territory_screen": screen,
        "candidates": [e.brief(case.weeks, None if e.territory == "ALL" else case.contaminated(e, case.episode_weeks(e)))
                       for e in case.discover()],
        "territory_ids": case_territories(),
    }, indent=1)


def case_territories() -> list[str]:
    from .sql import TERRITORIES
    return TERRITORIES


def investigate(case: Case, spec: str, on_step=None) -> dict:
    """Run the model investigator on `case` in place. Returns trajectory facts for the envelope."""
    lock = threading.RLock()  # a model may call tools in parallel; one DuckDB connection and one case take one at a time
    stats = {"tool_calls": 0, "refused": 0, "llm_calls": 0, "finished": False, "fallback": None, "capped": None}
    by = "agent"

    def step(name: str, args: dict, result: str) -> str:
        stats["tool_calls"] += 1
        if on_step:
            on_step({"tool": name, "args": args, "result": result[:400]})
        return result

    def guard(name: str, args: dict, fn) -> str:
        with lock:
            return _guard(name, args, fn)

    def _guard(name: str, args: dict, fn) -> str:
        if stats["finished"]:
            return "The investigation is finished. Reply with one short sentence and stop calling tools."
        if stats["tool_calls"] >= MAX_TOOL_CALLS:
            stats["capped"] = "tool_calls"
            return step(name, args, "Refused: the tool-call budget is spent. Call finish now.")
        try:
            return step(name, args, fn())
        except Refused as exc:
            stats["refused"] += 1
            return step(name, args, f"Refused: {exc}")

    @tool
    def compare(episode_id: Annotated[str, "A candidate episode id, e.g. E1"],
                exclude_controls: Annotated[list[str] | None, "Territory ids to leave out of the controls"] = None) -> str:
        """Compare one episode with control territories (for a launch: the share loss). exclude_controls is usually empty: list only territories named in the episode's controls_with_own_episode. Returns a comparison id to use in accept_driver."""
        def run() -> str:
            k = case.compare(episode_id, exclude_controls or [])
            return json.dumps({"comparison_id": k.id, "episode": k.episode, "method": k.method, "controls": k.controls,
                               "stats": k.stats, "flags": k.flags})
        return guard("compare", {"episode_id": episode_id, "exclude_controls": exclude_controls}, run)

    @tool
    def accept_driver(episode_id: Annotated[str, "Episode id"], comparison_id: Annotated[str, "Comparison id, e.g. K1"],
                      reason: Annotated[str, "Why, in words only (no digits)"]) -> str:
        """Accept an episode as a driver of the miss, quantified by the given comparison."""
        def run() -> str:
            case.accept(episode_id, comparison_id, reason, by)
            return f"Accepted {episode_id} using {comparison_id}."
        return guard("accept_driver", {"episode_id": episode_id, "comparison_id": comparison_id, "reason": reason}, run)

    @tool
    def reject_driver(episode_id: Annotated[str, "Episode id"], reason: Annotated[str, "Why, in words only (no digits)"]) -> str:
        """Reject an episode as a driver of the miss."""
        def run() -> str:
            case.reject(episode_id, reason, by)
            return f"Rejected {episode_id}."
        return guard("reject_driver", {"episode_id": episode_id, "reason": reason}, run)

    @tool
    def abstain(reason: Annotated[str, "Why no explanation can be supported, in words only"]) -> str:
        """Stop without attributing the miss."""
        def run() -> str:
            case.abstain(reason, by)
            return "Abstained. Call finish."
        return guard("abstain", {"reason": reason}, run)

    @tool
    def finish(note: Annotated[str, "One sentence in words on what you decided"] = "") -> str:
        """End the investigation."""
        with lock:
            return _finish(note)

    def _finish(note: str) -> str:
        if stats["finished"]:
            return "The investigation is finished. Reply with one short sentence and stop calling tools."
        open_ = [e.id for e in case.episodes.values() if e.status == "candidate"]
        if open_ and not stats.get("warned_open") and stats["tool_calls"] < MAX_TOOL_CALLS:
            stats["warned_open"] = True
            return step("finish", {"note": note}, f"Not finished: still undecided {', '.join(open_)}. Decide each, then call finish again.")
        stats["finished"] = True
        return step("finish", {"note": note}, "Done. Undecided episodes stay listed as not tested." if open_ else "Done.")

    async def run_agent() -> None:
        opts = chat_options(spec)
        agent = Agent(client=chat_client(spec), name="forecast_investigator", instructions=open(PROMPT, encoding="utf-8").read(),
                      tools=[compare, accept_driver, reject_driver, abstain, finish], default_options=opts)
        task = ("Investigate this forecast miss. Decide every candidate with the tools, then call finish.\n\n" + briefing(case))
        stats["llm_calls"] += 1
        await agent.run(task)
        # One nudge if the model stopped talking with candidates still open.
        if not stats["finished"] and any(e.status == "candidate" for e in case.episodes.values()) \
                and stats["tool_calls"] < MAX_TOOL_CALLS and stats["capped"] is None:
            stats["llm_calls"] += 1
            await agent.run("Some candidates are still undecided. Decide each with accept_driver or reject_driver, then call finish.")

    started = time.time()
    case.discover()
    try:
        asyncio.run(asyncio.wait_for(run_agent(), timeout=WALL_SECONDS))
    except asyncio.TimeoutError:
        stats["capped"] = "wall_clock"
    except Exception as exc:  # a failed model is a defined exit: the rules decide what is still open
        stats["fallback"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    if stats["fallback"]:
        run_rules(case, by="rules (fallback)", only_pending=True)
    # A candidate the agent never decided is decided by the rules, and labelled so, rather than silently dropped.
    open_ = [e.id for e in case.episodes.values() if e.status == "candidate"]
    stats["left_undecided"] = len(open_)
    if open_ and not case.abstained:
        run_rules(case, by="rules (agent left it undecided)", only_pending=True)
    stats["agent_seconds"] = round(time.time() - started, 1)
    return stats
