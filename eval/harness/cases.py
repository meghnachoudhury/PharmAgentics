"""The golden case model and loader. One YAML file per persona question."""
from __future__ import annotations

import hashlib
from typing import Literal

import yaml
from pydantic import BaseModel

from .paths import GOLDEN_DIR

Lane = Literal["briefing", "forecast"]


class Fact(BaseModel):
    """A number or label from the story, with the read-only SQL that recomputes it."""

    id: str
    value: int | float | str
    sql: str


class MustNotSay(BaseModel):
    text: str
    phrases: list[str] = []  # checked by code: any appearance fails the case
    semantic: list[str] = []  # quoted but context-dependent ("... without the plan"); judge only


class FollowUp(BaseModel):
    """A second turn on the brief the first question produced (brief-006 FR-013)."""

    question: str
    section: str | None = None  # the section an analyst pinned ("3.1"), if any
    then: str
    must_not_say: MustNotSay | None = None


class Case(BaseModel):
    id: str
    lane: Lane
    story: str
    persona: str
    category: str | None = None  # Evaluation Pack §4 taxonomy (Briefing)
    scenario: str | None = None  # TC-01 to TC-12 (Forecast); Alvin and Sienna assign
    split: Literal["dev", "held_out"] = "dev"
    status: Literal["draft", "frozen"] = "draft"
    question: str
    review_note: str | None = None
    period: str | None = None
    anchor: str | None = None
    story_text: str
    given: str
    when: str
    then: str
    reference_answer: str
    must_not_say: MustNotSay
    action: str | None = None
    eval_items: list[str]
    facts: list[Fact] = []
    follow_up: FollowUp | None = None  # two-turn cases (brief-006 FR-013)
    source: str

    def inputs(self) -> dict:
        """What the system under test receives: the question, and the follow-up for a two-turn case."""
        return {"question": self.question, "follow_up": self.follow_up.question if self.follow_up else None,
                "section": self.follow_up.section if self.follow_up else None}

    def expectations(self) -> dict:
        """What the scorers compare against. Only `expected_response` reaches an LLM judge."""
        later = self.follow_up.must_not_say.phrases if self.follow_up and self.follow_up.must_not_say else []
        return {
            "expected_response": self.reference_answer,
            "case_id": self.id,
            "story": self.story,
            "lane": self.lane,
            "must_not_say": self.must_not_say.phrases + later,
            "golden_numbers": [f.value for f in self.facts if isinstance(f.value, (int, float))],
            "eval_items": self.eval_items,
        }


def case_files(lane: str | None = None):
    lanes = [lane] if lane and lane != "all" else ["briefing", "forecast"]
    return sorted(p for name in lanes for p in (GOLDEN_DIR / name).glob("*.yaml"))


def load_cases(lane: str | None = None, stories: list[str] | None = None) -> list[Case]:
    cases = [Case.model_validate(yaml.safe_load(p.read_text(encoding="utf8"))) for p in case_files(lane)]
    if stories:
        wanted = {s.upper() for s in stories}
        cases = [c for c in cases if c.story in wanted or c.id in wanted]
    return sorted(cases, key=lambda c: c.id)


def golden_fingerprint(lane: str | None = None) -> str:
    digest = hashlib.sha256()
    for path in case_files(lane):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
