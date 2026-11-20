"""Approved lessons for the agents (core-008 FR-022; ADR 0003).

Agents read only `agents/brand-briefing/knowledge/lessons.yaml`: lessons a person approved and a pull request
merged. They never read threads or raw feedback. `PHARMAGENTICS_TRIAL_LESSONS` (a JSON list of lesson texts) adds
draft lessons for one process; only `python -m eval improve` sets it, to rerun a flagged question with a draft
lesson before anyone approves it. The app never sets it.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

FILE = Path(__file__).resolve().parents[1] / "knowledge" / "lessons.yaml"
TRIAL = "PHARMAGENTICS_TRIAL_LESSONS"


def approved(applies_to: str = "writer") -> list[str]:
    data = yaml.safe_load(FILE.read_text(encoding="utf-8")) if FILE.is_file() else None
    return [str(x["text"]).strip() for x in (data or {}).get("lessons") or []
            if x.get("text") and x.get("applies_to", "writer") == applies_to]


def trial() -> list[str]:
    try:
        return [str(t).strip() for t in json.loads(os.environ.get(TRIAL) or "[]") if str(t).strip()]
    except ValueError:
        return []


def block(applies_to: str = "writer") -> str:
    """The lines appended to a prompt; empty when there is no lesson, so the prompt is unchanged."""
    items = [t for t in approved(applies_to) + trial() if not re.search(r"\d", t)]  # a lesson never carries a number
    return ("\n\nLessons from the team's review (follow them; they never override the rules above):\n"
            + "\n".join(f"- {t}" for t in items)) if items else ""
