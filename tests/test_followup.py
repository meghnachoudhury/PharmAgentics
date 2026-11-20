"""brief-006 slice 3: scripted follow-ups answer from the brief alone (FR-004, FR-005, FR-007; brief-003 FR-023)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.tools import DEFAULT_DB  # noqa: E402
from pharmagentics.tools.followup import answer, suggestions  # noqa: E402

needs_db = pytest.mark.skipif(not DEFAULT_DB.exists(), reason="build it with: uv run python src/pharmagentics/data/load_duckdb.py")


def stored(territory: str, week: str) -> dict:
    """A brief as the API stores it: the scripted envelope plus its scope."""
    from briefing_baseline import answer as brief

    env = brief(f"Week of {week} in {territory.replace('_', ' ').title()}: Generate the weekly brand-performance briefing.")
    return {**env, "brand_id": "BXA", "territory_id": territory, "week_start": week}


@pytest.fixture(scope="module")
def pacific():
    return stored("PACIFIC", "2026-06-08")


@pytest.fixture(scope="module")
def new_england():
    return stored("NEW_ENGLAND", "2026-05-04")


def untraced(turn: dict) -> list[str]:
    text = re.sub(r"§\s*\d(?:\.\d+)?", " ", turn["answer"])  # section references are identifiers
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\w*[A-Za-z_]\w*\d\w*\b", " ", text)
    values = {c["value"] for c in turn["claims"]}
    return [n for n in re.findall(r"\d[\d,.]*%?", text) if n.rstrip(".,") not in values]


@needs_db
def test_a_section_question_restates_that_section_with_its_own_claims(pacific):
    turn = answer(pacific, "What did the checks find?", section="3.1")
    assert turn["kind"] == "restate" and turn["cited"] == ["3.1"]
    assert turn["answer"].startswith("§3.1 Pacific:") and "Supply: supported" in turn["answer"]
    assert turn["claims"] and not untraced(turn)
    assert {e["id"] for e in turn["evidence"]} == {c["evidence_id"] for c in turn["claims"]}


@needs_db
def test_a_section_reference_in_the_text_is_followed(pacific):
    assert answer(pacific, "Tell me more about §5")["cited"] == ["5"]
    assert answer(pacific, "What is this brief least sure of?")["cited"] == ["1"]  # no reference: the Bottom line
    assert answer(pacific, "And §9?")["kind"] == "no_section"


@needs_db
def test_a_number_the_brief_does_not_hold_is_never_invented(pacific):
    turn = answer(pacific, "Split this by plan", section="3.1")
    assert turn["kind"] == "not_in_brief" and turn["offer"] == {"agent": True} and not turn["claims"]
    assert not re.search(r"\d", re.sub(r"§\s*\d(?:\.\d+)?", "", turn["answer"]))


@needs_db
def test_another_scope_gets_an_offer_and_the_brief_stays(pacific):
    turn = answer(pacific, "What about BXE in South Central?")
    assert turn["kind"] == "out_of_scope"
    assert turn["offer"] == {"brand": "BXE", "territory": "SOUTH_CENTRAL", "week": "2026-06-08"}
    assert "stays as it is" in turn["answer"] and not turn["claims"]
    assert answer(pacific, "How did 2026-05-04 look?")["offer"]["week"] == "2026-05-04"


@needs_db
def test_no_driver_for_a_projected_cut(new_england):
    turn = answer(new_england, "Why did New England drop?")
    assert turn["kind"] == "no_driver" and "projected, an assumption" in turn["answer"] and turn["cited"] == ["4"]


@needs_db
def test_every_section_gets_suggestions_the_scripted_engine_can_answer(pacific):
    tips = suggestions(pacific["sections"])
    assert set(tips) >= {"1", "2", "3", "3.1", "4", "5"}
    for number, items in tips.items():
        for q in items:
            turn = answer(pacific, q, section=number)
            assert turn["kind"] in {"restate", "not_in_brief"} and not untraced(turn), (number, q)
