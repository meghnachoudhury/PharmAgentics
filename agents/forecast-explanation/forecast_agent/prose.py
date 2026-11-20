"""Step 8 with a model: a plain-language summary for a brand lead. The model writes with claim tokens only; code
fills every number. The text is refused, and the code summary kept, if it holds a stray digit or an unknown
token, leaves out the residual, adds a driver or territory the report does not name, recommends a commercial
action, or uses a term the project bans. The action and new-driver checks follow feagent/writer.py."""
from __future__ import annotations

import asyncio
import os
import re
from typing import Annotated

from pharmagentics.tools.queries import TERRITORY_NAMES, name
from pharmagentics.tools.registry import digits_outside_tokens

from . import sql as S

WRITE_SECONDS = float(os.environ.get("FORECAST_WRITER_SECONDS", "120"))
MAX_CHARS = 700

_LEVER = r"(?:forecast|price|pricing|budget|spend|spending|target|targeting|quota|discount)"
_VERB = r"(?:lower|raise|increase|decrease|cut|adjust|change|revise|reduce|boost|shift|move)(?:ing|s|d|ed)?"
ACTIONS = (
    re.compile(rf"\b(?:should|recommend(?:s|ed)?|consider(?:ing)?|suggest(?:s|ed)?|advis(?:e|es|ed)|propos(?:e|es|ed)|"
               rf"need(?:s)? to|must|ought to)\b[^.;]{{0,40}}\b{_VERB}\b[^.;]{{0,40}}\b{_LEVER}\b", re.I),
    re.compile(rf"(?:^|[.;:]\s+){_VERB}\b(?!\s+in\b)[^.;]{{0,40}}\b{_LEVER}\b", re.I),
    re.compile(r"\b(?:recommend\w*|consider\w*|suggest\w*|propos\w*)\b[^.;]{0,40}\b(?:discount|price|pricing|budget|targeting|quota)\b", re.I),
    re.compile(r"\b(?:reallocat\w*|rebalanc\w*|re-?target\w*|discounting|price (?:cut|increase|change|reduction))\b", re.I),
)
CATEGORIES = {
    "access": re.compile(r"\b(payer|formulary|access|tier|prior authori[sz]ation|step therapy)\b", re.I),
    "promotion": re.compile(r"\b(promo\w*|rep calls?|field force|coverage lapse|sales reps?)\b", re.I),
    "supply": re.compile(r"\b(supply|stock-?outs?|inventory|backorders?)\b", re.I),
    "competitor": re.compile(r"\b(competitor\w*|competitive|metacora|launch\w*|rival)\b", re.I),
}
BANNED = re.compile(r"\b(surveillance|new patients?)\b", re.I)

PROMPT = """You write the summary of a forecast-miss report for a pharmaceutical brand lead: two to four short
sentences in plain language. Use only the facts given. Every number must be written as its token exactly, for
example {c3}; never type a digit yourself. Percent tokens already include the % sign, so never write "percent"
after them. Say how big the miss was, what explains most of it and how sure we
are, and how much is not explained yet. Do not recommend any action, do not add a cause, region or product that
is not in the facts, and do not use the words "surveillance" or "new patients". Call submit_summary once."""


def facts(w, parts: list[dict]) -> tuple[list[dict], dict]:
    """Claim tokens for the summary, and what a valid text may mention."""
    case, out = w.case, []

    def add(means: str, sql: str, fmt: str = "int") -> str:
        token = w.c("summary", sql, fmt)
        out.append({"token": token, "means": means})
        return token

    add("the miss as a percent of forecast (below forecast)" if w.V < 0 else "the miss as a percent of forecast (above forecast)",
        S.pct_of_forecast(w.W, w.cut), "pct1")
    add("the miss in TRx (actual minus forecast)", w.v_sql)
    allowed_drivers, territories = set(), {w.cut}
    for p in parts:
        if p["episode"] is None:
            add("the usual forecast bias in TRx", p["sql"])
            continue
        level, _ = case.confidence(p["episode"], p["comparison"])
        add(f"{p['label']}: contribution in TRx (confidence {level})", p["sql"])
        add(f"{p['label']}: share of the miss", S.share_of(p["sql"], w.v_sql), "pct1")
        allowed_drivers.add(p["driver"])
        territories.add(p["territory"])
    residual = add("the unexplained residual in TRx", S.minus(w.v_sql, [p["sql"] for p in parts]))
    add("the unexplained residual as a share of the miss",
        S.share_of(S.minus(w.v_sql, [p["sql"] for p in parts]), w.v_sql), "pct1")
    period = (f"the week of {w.W[0]}" if len(w.W) == 1 else f"the weeks of {w.W[0]} to {w.W[-1]}")
    scope = {"brand": "Cardiovela (BXA)", "where": "nationally" if w.cut == "NATIONAL" else name(w.cut), "period": period}
    return out, {"drivers": allowed_drivers, "territories": territories, "residual": residual, "scope": scope}


def check(text: str, tokens: list[dict], allowed: dict) -> str | None:
    """None if the text may be shown, else why it was refused."""
    text = " ".join(text.split())
    if not text or len(text) > MAX_CHARS:
        return "length"
    if digits_outside_tokens(text):
        return "digit_outside_token"
    used = set(re.findall(r"\{c\d+\}", text))
    if used - {t["token"] for t in tokens}:
        return "unknown_token"
    if allowed["residual"] not in used and "not explained" not in text.lower() and "unexplained" not in text.lower():
        return "residual_missing"
    if any(p.search(text) for p in ACTIONS):
        return "commercial_action"
    if BANNED.search(text):
        return "banned_term"
    for driver, pattern in CATEGORIES.items():
        if pattern.search(text) and driver not in allowed["drivers"]:
            return "new_driver"
    for tid, label in TERRITORY_NAMES.items():
        if tid != "NATIONAL" and re.search(rf"\b{re.escape(label)}\b", text) and tid not in allowed["territories"]:
            return "new_territory"
    return None


def write_summary(w, parts: list[dict], spec: str) -> tuple[str | None, str]:
    """The summary template (claim tokens unfilled) and a status: ok, or why the code summary is kept."""
    from agent_framework import Agent, tool

    from pharmagentics.llm import chat_client, chat_options

    tokens, allowed = facts(w, parts)
    got: dict = {}

    @tool
    def submit_summary(summary: Annotated[str, "Two to four sentences; numbers only as tokens like {c3}"]) -> str:
        """Submit the summary."""
        got["text"] = summary
        return "Received. Stop."

    lines = "\n".join(f"{t['token']} = {t['means']}" for t in tokens)
    task = (f"Report on {allowed['scope']['brand']}, {allowed['scope']['where']}, {allowed['scope']['period']}.\n"
            f"Facts (token = meaning):\n{lines}")
    agent = Agent(client=chat_client(spec), name="summary_writer", instructions=PROMPT, tools=[submit_summary],
                  default_options=chat_options(spec))
    try:
        asyncio.run(asyncio.wait_for(agent.run(task), timeout=WRITE_SECONDS))
    except Exception:  # noqa: BLE001 - the code summary stands
        return None, "model_error"
    text = " ".join(str(got.get("text") or "").split())
    if not text:
        return None, "no_text"
    reason = check(text, tokens, allowed)
    return (None, reason) if reason else (text, "ok")
