"""Step 1 with a model: read a question into a scope. The model fills one tool call (period as calendar dates,
territory, intent); code checks every field against the release and turns the period into Monday weeks. If the
model fails, returns nothing usable or names something outside the release, the keyword rules read it instead.
The analyst still confirms the scope card before anything runs."""
from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta
from typing import Annotated

from pharmagentics.tools.queries import TERRITORY_NAMES, iso, mondays

from .scope import INTENTS, Scope, parse_scope

READ_SECONDS = float(os.environ.get("FORECAST_SCOPE_SECONDS", "120"))

PROMPT = """You read an analyst's question about the gap between the locked weekly TRx forecast and the actual for
Cardiovela (BXA), a fictional brand, and call set_scope exactly once. Do not answer the question.

The data runs from {first} to {latest}. Today is the week of {latest}; read relative periods ("last August",
"this summer", "Q3", "the last three months") against it. Seasons: spring Mar to May, summer Jun to Aug, fall
Sep to Nov, winter Dec to Feb. Q1 Jan to Mar, Q2 Apr to Jun, Q3 Jul to Sep, Q4 Oct to Dec.
- period_start and period_end are calendar dates (YYYY-MM-DD) covering what the question asks about. A month,
  quarter, season or year means its whole span: "June 2026" is 2026-06-01 to 2026-06-30. Only a single day or
  "the week of" a day is one week: give that date for both. If no period is given, give {latest} for both.
- territory is one of: {territories}. Use NATIONAL when no territory is named or for "national", "overall",
  "which region" or "where".
- intent is one of:
{intents}
- out_of_scope is a short reason in words when the question asks about another product's forecast or asks to
  change a forecast, price, budget or targeting; otherwise leave it empty.

Examples (today is the week of 2026-10-05):
- "Why were we below plan in the Southeast last August?" -> 2026-08-01 to 2026-08-31, SOUTHEAST, drivers
- "Which region hurt us most this summer?" -> 2026-06-01 to 2026-08-31, NATIONAL, where
- "How much of the Q3 2026 shortfall is Metacora?" -> 2026-07-01 to 2026-09-30, NATIONAL, attribution
- "Is the New England number for May 4 2026 trustworthy?" -> 2026-05-04 to 2026-05-04, NEW_ENGLAND, reliability
- "Top five gaps over the last three months" -> 2026-07-06 to 2026-10-05, NATIONAL, screen
"How much" and "split" questions are attribution; "why" and "what caused" questions are drivers. Questions about
which regions, territories or segments a miss sits in are where, even when they say "drive". Questions about how
big the miss is are where; reliability is only for doubts about the data itself (provisional, a feed problem)."""


def _period(start: str, end: str, first: str, latest: str) -> list[str]:
    """Calendar dates to the Monday weeks of the release: one date (or under a week) is the week holding it;
    a longer span is every week whose Monday falls inside it."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if b < a:
        a, b = b, a
    if (b - a).days < 7:
        w = iso(a - timedelta(days=a.weekday()))
        return [w] if first <= w <= latest else []
    a = a + timedelta(days=(7 - a.weekday()) % 7)
    b = b - timedelta(days=b.weekday())
    return [w for w in mondays(iso(a), iso(b)) if first <= w <= latest] if a <= b else []


def read_scope(question: str, first: str, latest: str, spec: str) -> tuple[Scope, str]:
    """The scope and who read it: "model", or "rules" when the model's reading was unusable."""
    rules = parse_scope(question, first, latest)
    if rules.out_of_scope and "outside the release" not in rules.out_of_scope:
        return rules, "rules"  # code's own refusals (another product, a commercial action) always stand
    from agent_framework import Agent, tool

    from pharmagentics.llm import chat_client, chat_options

    got: dict = {}

    @tool
    def set_scope(period_start: Annotated[str, "YYYY-MM-DD"], period_end: Annotated[str, "YYYY-MM-DD"],
                  territory: Annotated[str, "A territory id or NATIONAL"], intent: Annotated[str, "One intent id"],
                  out_of_scope: Annotated[str, "A reason in words, or empty"] = "") -> str:
        """Record how the question should be read."""
        got.update(start=period_start, end=period_end, territory=territory, intent=intent, out_of_scope=out_of_scope)
        return "Recorded. Stop."

    instructions = PROMPT.format(first=first, latest=latest, territories=", ".join(TERRITORY_NAMES),
                                 intents="\n".join(f"  {k}: {v}" for k, v in INTENTS.items()))
    agent = Agent(client=chat_client(spec), name="scope_reader", instructions=instructions, tools=[set_scope],
                  default_options=chat_options(spec))
    try:
        asyncio.run(asyncio.wait_for(agent.run("Question: " + question), timeout=READ_SECONDS))
        weeks = _period(got["start"], got["end"], first, latest)
    except Exception:  # noqa: BLE001 - no usable reading: the rules read it
        return rules, "rules"
    territory = str(got.get("territory", "")).upper().replace(" ", "_").replace("-", "_")
    intent = str(got.get("intent", "")).strip()
    if not weeks or territory not in TERRITORY_NAMES or intent not in INTENTS:
        return rules, "rules"
    reason = " ".join(str(got.get("out_of_scope") or "").split())[:200]
    if any(ch.isdigit() for ch in reason):
        reason = "The question is outside what this agent explains."
    return Scope(question=rules.question, weeks=weeks, territory=territory, intent=intent,
                 notes=[f"Read by the model as {weeks[0]}" + (f" to {weeks[-1]}" if len(weeks) > 1 else "") + "."],
                 out_of_scope=reason or None), "model"
