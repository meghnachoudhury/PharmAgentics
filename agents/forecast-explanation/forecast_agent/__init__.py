"""Forecast-Explanation agent (fcst-001 redesign): question in, code-parsed scope, data-discovered episodes,
an investigator that chooses comparisons and verdicts, code-written answer.

    answer(question)                 the rules policy (no model): the scripted arm and the fallback
    answer(question, model=spec)     the model investigator, e.g. "ollama:qwen3:4b-instruct-2507-q4_K_M"
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from pharmagentics.tools import DEFAULT_DB, Registry

from .engine import Case
from .policy import run_rules
from .scope import parse_scope
from .write import compose

HERE = Path(__file__).resolve().parent


def config_version() -> str:
    """A hash of the engine's own files, so a changed prompt or rule shows as a new configuration in MLflow."""
    h = hashlib.sha256()
    for p in sorted(HERE.glob("*.py")) + sorted((HERE / "prompts").glob("*")):
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def context(db=DEFAULT_DB) -> tuple[str, str]:
    reg = Registry(db)
    try:
        return reg.rows("select min(week_start)::varchar, max(week_start)::varchar from raw.calendar")[0]
    finally:
        reg.close()


def answer(question: str, model: str | None = None, db=DEFAULT_DB, territory: str | None = None,
           weeks: list[str] | None = None, on_step=None, drop_controls: list[str] | None = None) -> dict:
    started = time.time()
    reg = Registry(db)
    try:
        first, latest = reg.rows("select min(week_start)::varchar, max(week_start)::varchar from raw.calendar")[0]
        scope = parse_scope(question, first, latest, territory=territory, weeks=weeks)
        if scope.out_of_scope:
            return {"system": "forecast_agent", "answer": scope.out_of_scope, "claims": [], "evidence": [],
                    "abstained": True, "report": {"out_of_scope": scope.out_of_scope, "scope": scope.card(),
                                                  "question": scope.question, "intent": scope.intent}}
        case = Case(reg, scope, drop_controls)
        trajectory = {"model": model, "tool_calls": 0, "llm_calls": 0, "fallback": None}
        if scope.intent == "screen" or case.cut_provisional():
            run_rules(case, "code") if case.cut_provisional() else None
            mode = "code"
        elif model:
            from .agent import investigate
            trajectory.update(investigate(case, model, on_step=on_step))
            mode = f"agent ({model})" + (" with rules fallback" if trajectory.get("fallback") else "")
        else:
            run_rules(case)
            mode = "rules"
        trajectory["seconds"] = round(time.time() - started, 1)
        out = compose(case, mode, trajectory)
        out["system"] = "forecast_agent" if model else "forecast_rules"
        return out
    finally:
        reg.close()
