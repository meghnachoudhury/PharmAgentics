"""Strict, independent API contracts. Runtime packages must not import eval/."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Territory = Literal[
    "GREAT_LAKES", "MID_ATLANTIC", "MOUNTAIN", "NEW_ENGLAND",
    "NORTHWEST", "PACIFIC", "SOUTHEAST", "SOUTH_CENTRAL", "NATIONAL",
]
Brand = Literal["BXA", "BXC"]


class BrandCapability(BaseModel):
    id: Brand
    name: str
    engines: list[Literal["scripted", "agent"]]


class TriageDecision(BaseModel):
    """P1's decision on a triage plan (brief-002 FR-023): the stories to investigate, in order."""
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(pattern=r"^t-[0-9a-f]{12}$")
    stories: list[str] = Field(default_factory=list, max_length=10)


class BriefingQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["weekly_brief"] = "weekly_brief"
    brand_id: Brand = "BXA"
    territory_id: Territory = "PACIFIC"
    week_start: date
    question: str = Field(default="What changed this week?", min_length=3, max_length=300)
    triage: TriageDecision | None = None  # brief-002: absent = the code plan, unchanged behavior

    @field_validator("week_start")
    @classmethod
    def reporting_week_must_start_on_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("week_start must be a Monday (reporting week start)")
        return value


class Claim(BaseModel):
    value: str
    evidence_id: str


class Evidence(BaseModel):
    id: str
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    query: str | None = None
    result: Any = None
    data_version: str | None = None


class BriefingResult(BaseModel):
    """What the engine returns. The API adds brief_id, view and the review state (views.analyst)."""
    status: Literal["draft_requires_review"] = "draft_requires_review"
    review_status: Literal["not_submitted"] = "not_submitted"
    engine: Literal["scripted", "agent"] = "scripted"  # agent: posted by the owner's local worker (core-007 FR-028)
    system: str
    question: str
    brand_id: Brand = "BXA"
    territory_id: Territory
    week_start: date
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    data_version: str | None = None
    abstained: bool = False
    # brief-002 Phase A, analyst view only (never in the leadership allow-list):
    triage: dict[str, Any] | None = None  # TriageRecord: who made each triage call
    flow: list[dict[str, Any]] | None = None  # StageFlow: the seven stages, states and actors
    citations: list[dict[str, int]] | None = None  # where each claim value sits in `answer`: {start, end, claim}
    # brief-003: the memo's sections with charts and the data behind them; leaders get views.leadership_sections
    sections: list[dict[str, Any]] | None = None


class ReleaseContext(BaseModel):
    first_week: date
    latest_week: date
    brand_id: Brand | None = "BXA"
    territory_ids: list[str]
    available_weeks: list[date] = Field(default_factory=list)
    product_ids: list[Brand] = Field(default_factory=lambda: ["BXA"])
    brands: list[BrandCapability] = Field(default_factory=lambda: [
        BrandCapability(id="BXA", name="Cardiovela", engines=["scripted", "agent"])])
    supported_intents: list[Literal["weekly_brief"]] = Field(default_factory=lambda: ["weekly_brief"])
    engine: Literal["scripted"] = "scripted"


class ViewAs(BaseModel):
    """The test login's choice: the analyst roles (P1, CA) or the leadership roles (P3, BM) of both lanes."""
    model_config = ConfigDict(extra="forbid")

    view: Literal["analyst", "leadership"]


class ReviewRequest(BaseModel):
    """The analyst's decision on one brief (core-007 FR-010). A rejection needs a reason."""
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class InsightMark(BaseModel):
    """The participant marks that they have what they need (time to insight, FR-025)."""
    model_config = ConfigDict(extra="forbid")

    brief_id: str = Field(min_length=3, max_length=40)
    view: Literal["analyst", "leadership"]


class AgentJobRequest(BaseModel):
    """An agent job for the owner's local worker (core-007 FR-028; brief-002 Phase B)."""
    model_config = ConfigDict(extra="forbid")

    kind: Literal["triage", "brief"]
    query: BriefingQuery
    triage_job: str | None = Field(default=None, pattern=r"^j-[0-9a-f]{12}$")  # brief: the reviewed plan's job
    decision: TriageDecision | None = None  # brief: P1's decision on that plan


class WorkerPoll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, max_length=120)
    worker: str = Field(default="worker", min_length=1, max_length=60, pattern=r"^[\w.@-]+$")  # which teammate's machine


class WorkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=2000)


class ForecastRunRequest(BaseModel):
    """One Forecast explanation request. The engine and model are fixed by the server, never by the caller."""
    model_config = ConfigDict(extra="forbid")

    territory_id: Territory = "NATIONAL"
    week_start: date
    window_weeks: int = Field(default=1, ge=1, le=52)
    view: Literal["analyst", "leadership"] | None = None


class ForecastAsk(BaseModel):
    """A question for the Forecast agent (fcst-001). The scope card's edits may override the parsed territory and
    weeks. The engine and model are fixed by the server, never by the caller."""
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=400)
    territory_id: Territory | None = None
    week_from: date | None = None
    week_to: date | None = None
    intent: Literal["reliability", "screen", "where", "drivers", "attribution", "unknowns", "next_checks",
                    "assumptions", "audit", "communicate"] | None = None
    view: Literal["analyst", "leadership"] | None = None

    @field_validator("question")
    @classmethod
    def tidy(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("Ask a question of at least three characters.")
        return value


class ForecastFollowup(BaseModel):
    """A follow-up question on one finished Forecast question run."""
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=300)


class ForecastReview(BaseModel):
    """The Brand Manager's decision on a submitted Forecast run. Rejecting or returning needs a note."""
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected", "returned"]
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def strip(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None
