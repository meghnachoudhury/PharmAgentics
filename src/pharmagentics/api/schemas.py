"""Strict, independent API contracts. Runtime packages must not import eval/."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Territory = Literal[
    "GREAT_LAKES", "MID_ATLANTIC", "MOUNTAIN", "NEW_ENGLAND",
    "NORTHWEST", "PACIFIC", "SOUTHEAST", "SOUTH_CENTRAL", "NATIONAL",
]


class BriefingQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["weekly_brief"] = "weekly_brief"
    brand_id: Literal["BXA"] = "BXA"
    territory_id: Territory = "PACIFIC"
    week_start: date
    question: str = Field(default="What changed this week?", min_length=3, max_length=300)

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
    engine: Literal["scripted"] = "scripted"
    system: str
    question: str
    brand_id: Literal["BXA"] = "BXA"
    territory_id: Territory
    week_start: date
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    data_version: str | None = None
    abstained: bool = False


class ReleaseContext(BaseModel):
    first_week: date
    latest_week: date
    brand_id: Literal["BXA"] = "BXA"
    territory_ids: list[str]
    available_weeks: list[date] = Field(default_factory=list)
    product_ids: list[Literal["BXA"]] = Field(default_factory=lambda: ["BXA"])
    supported_intents: list[Literal["weekly_brief"]] = Field(default_factory=lambda: ["weekly_brief"])
    engine: Literal["scripted"] = "scripted"


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
