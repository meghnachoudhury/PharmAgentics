"""Scope gate (brief-002 FR-025; Nov 6 trace C-024). Code, not a model: questions the data cannot answer
get the scripted brief plus a statement of what the data cannot rank, and the loop never starts."""
from __future__ import annotations

import re

_RULES = [
    (r"\b(next|where should|how should|best|better)\b.*\b(dollar|spend|budget|invest|money|channel)s?\b|\b(rank|allocate|allocation)\b.*\b(channel|spend|budget)s?\b",
     "The data cannot rank channels or spend: it holds aggregated promotion activity, not channel spend or its "
     "returns. What it supports is where coverage lapsed and what BXA did in those weeks; see the stories below."),
    (r"\b(roi|return on investment|attribut\w*|incremental lift)\b",
     "The data cannot measure ROI or attribute lift to a campaign: promotion is tested only as an association "
     "with a named comparison."),
    (r"\b(patient[- ]level|individual patients?|which patients|patient journey)\b",
     "The data has no patient-level records: it is aggregated by week, territory, plan and specialty."),
    (r"\b(forecast|next quarter|next month|predict|projection)\b",
     "This brief explains what happened; forecasts are the Forecast-Explanation agent's job."),
]


def out_of_scope(question: str) -> str | None:
    """The scope statement for a question the data cannot answer, else None. Only the text after the
    first colon is read, so the code-written 'Week of … in …:' prefix never triggers a rule."""
    ask = question.split(":", 1)[-1].lower()
    for pattern, statement in _RULES:
        if re.search(pattern, ask):
            return statement
    return None
