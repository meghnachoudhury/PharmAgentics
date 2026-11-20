"""Stage 1: turn a question into a scope (weeks, territory, intent). Code, not a model: the analyst sees the
scope card and can correct it, so a misread question is visible before anything is attributed."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from pharmagentics.tools.queries import TERRITORY_NAMES, iso, mondays
from pharmagentics.tools.window import parse

INTENTS = {
    "reliability": "Is the miss real, or a data issue?",
    "screen": "Rank the largest gaps",
    "where": "Where is the miss concentrated?",
    "drivers": "Which drivers plausibly contributed?",
    "attribution": "How much does each driver explain?",
    "unknowns": "How confident are we, and what is unexplained?",
    "next_checks": "What should be checked next, and by whom?",
    "assumptions": "Should forecast assumptions be reviewed?",
    "audit": "Can every finding be verified and reproduced?",
    "communicate": "A defensible summary for leadership",
}

# First match wins, so the narrower intents come first.
_INTENT_RULES = [
    ("screen", r"\b(top|largest|biggest|worst|rank\w*|list)\b"),
    ("reliability", r"\b(reliable|data issue|data problem|provisional|real miss|artifact)\b"),
    ("audit", r"\b(verif\w*|reproduc\w*|auditable|reconcil\w*|traceable)\b"),
    ("assumptions", r"\bassumptions?\b|\b(revise|review) the forecast\b"),
    ("communicate", r"\b(communicat\w*|defensibl\w*|leadership|executive)\b"),
    ("next_checks", r"\b(check next|checked next|which team|who should|next steps?)\b"),
    ("unknowns", r"\b(unexplained|unknown|remains?|confiden\w*|residual)\b"),
    ("where", r"\b(where|which (regions?|territor\w*|segments?)|concentrated)\b"),
    ("attribution", r"\b(how much|attribut\w*)\b"),
    ("drivers", r"\b(drivers?|hypothes\w*|candidate|contributed|caus\w*|why)\b"),
    ("attribution", r"\b(how much|attribut\w*|explain\w*|split|contribut\w*)\b"),
]

_OTHER_PRODUCT = re.compile(r"\b(for|of)\s+(metacora|lipidara|vascriva|bx[cde])\b", re.I)
_ACTION = re.compile(r"\b(should we|change|cut|raise|increase|reallocate)\b.*\b(price|budget|spend|targeting|forecast to|the forecast number)\b", re.I)
_RELATIVE = re.compile(r"\b(?:last|past|previous|recent)\s+(\d+|one|two|three|four|six|twelve)\s+(weeks?|months?)\b", re.I)
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "twelve": 12}


@dataclass
class Scope:
    question: str
    weeks: list[str]
    territory: str  # a territory id or NATIONAL
    intent: str
    notes: list[str] = field(default_factory=list)
    out_of_scope: str | None = None

    @property
    def period(self) -> str:
        if not self.weeks:
            return "no weeks"
        return f"week of {self.weeks[0]}" if len(self.weeks) == 1 else f"weeks {self.weeks[0]} to {self.weeks[-1]}"

    def card(self) -> dict:
        """What the analyst confirms before the investigation runs."""
        return {**asdict(self), "period": self.period, "territory_name": TERRITORY_NAMES.get(self.territory, self.territory),
                "intent_label": INTENTS[self.intent], "n_weeks": len(self.weeks)}


def intent_of(question: str) -> str:
    ask = question.split(":", 1)[-1].lower()
    for intent, pattern in _INTENT_RULES:
        if re.search(pattern, ask):
            return intent
    return "attribution"


def _relative(question: str, first: str, latest: str) -> list[str] | None:
    m = _RELATIVE.search(question)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else _WORDS[m.group(1).lower()]
    weeks = n if m.group(2).lower().startswith("week") else round(n * 52 / 12)
    end = date.fromisoformat(latest)
    start = max(date.fromisoformat(first), end - timedelta(days=7 * (weeks - 1)))
    return mondays(iso(start), iso(end))


def parse_scope(question: str, first: str, latest: str, territory: str | None = None,
                weeks: list[str] | None = None) -> Scope:
    """`territory` and `weeks` override the parse: the analyst's edits on the scope card."""
    question = " ".join(question.split())[:400]
    intent = intent_of(question)
    notes: list[str] = []
    if weeks is None:
        rel = _relative(question, first, latest)
        if rel is not None:
            weeks = rel
            notes.append(f"Read as weeks {rel[0]} to {rel[-1]}, counting back from the latest closed week.")
        else:
            ask = parse(question, first, latest)  # reads the period from the text before any colon
            weeks = ask["weeks"]
            if ask["note"]:
                notes.append(ask["note"])
            if ask["requested"] and len(ask["requested"]) != len(weeks):
                notes.append(f"Only weeks inside the release ({first} to {latest}) are used.")
            territory = territory or ask["territory"]
    if territory is None:
        territory = next((tid for tid, label in TERRITORY_NAMES.items()
                          if re.search(rf"\b{re.escape(label)}\b", question, re.I)), None)
    scope = Scope(question=question, weeks=sorted(weeks), territory=territory or "NATIONAL", intent=intent, notes=notes)
    if _OTHER_PRODUCT.search(question):
        scope.out_of_scope = ("Only Cardiovela (BXA) has a locked forecast in this release. Competitor products appear "
                              "here only as possible drivers of the Cardiovela miss.")
    elif _ACTION.search(question):
        scope.out_of_scope = ("This agent explains forecast misses. It does not change a forecast or recommend a "
                              "commercial action such as price, budget or targeting.")
    elif not scope.weeks:
        scope.out_of_scope = f"That period is outside the release, which runs from {first} to {latest}."
    return scope
