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
    # How an agent got there (tools called, LLM calls, tokens, cap hit). White-box and report-only:
    # no eval item scores it (black-box rule); it feeds the autonomy ledger's trajectory evidence.
    trajectory: dict | None = None
