"""What every system under test returns. Scorers read this, never the system's internals (black-box rule)."""
from __future__ import annotations

from pydantic import BaseModel


class Evidence(BaseModel):
    id: str
    tool: str
    params: dict = {}
    query: str | None = None
    result: object = None
    data_version: str | None = None


class Claim(BaseModel):
    value: str
    evidence_id: str


class AnswerEnvelope(BaseModel):
    system: str
    answer: str
    claims: list[Claim] = []
    evidence: list[Evidence] = []
    abstained: bool = False
    # The memo's sections (brief-003 FR-027): number, title, rendered text and prose, claim indexes. Scorers
    # read `answer`; this is for the app and for later item-level checks.
    sections: list[dict] | None = None
    # Two-turn cases (brief-006 FR-013): `answer`, `claims` and `evidence` hold the whole exchange (brief, then the
    # follow-up), so every gated check covers both turns; these say what the follow-up said and cited.
    follow_up_answer: str | None = None
    cited: list[str] | None = None  # section numbers the follow-up cites
    brief_sections: list[str] | None = None  # section numbers the brief has
    latency: dict | None = None  # seconds: {"brief": …, "turn": …}
    # How an agent got there (tools called, LLM calls, tokens, cap hit). White-box and report-only:
    # no eval item scores it (black-box rule); it feeds the autonomy ledger's trajectory evidence.
    trajectory: dict | None = None
