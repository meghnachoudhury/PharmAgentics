"""The golden set itself: one case per persona question, valid IDs, and numbers that recompute."""
import pytest

from eval.harness.cases import load_cases
from eval.harness.integrity import BRIEFING_STORIES, FORECAST_STORIES, check_facts, id_problems
from eval.harness.paths import DATABASE

CASES = load_cases()


def test_one_case_per_persona_question():
    """42 persona questions plus the six two-turn Briefing cases (brief-006 FR-013), one case each."""
    assert len(CASES) == 48
    assert {c.story for c in CASES if c.lane == "briefing"} == BRIEFING_STORIES
    assert {c.story for c in CASES if c.lane == "forecast"} == FORECAST_STORIES
    assert len({c.id for c in CASES}) == 48
    assert {c.story for c in CASES if c.follow_up} == {f"FU-{n}" for n in range(1, 7)}


def test_eval_items_exist_in_their_lane():
    assert id_problems(CASES) == []


def test_every_case_has_a_question_an_answer_and_a_rule():
    for c in CASES:
        assert c.question.strip() and c.reference_answer.strip() and c.must_not_say.text.strip(), c.story


def test_only_dev_cases_live_in_the_repo():
    assert {c.split for c in CASES} == {"dev"}


@pytest.mark.skipif(not DATABASE.exists(), reason="build it with: uv run python src/pharmagentics/data/load_duckdb.py")
def test_every_fact_recomputes_from_the_data():
    bad = [r for r in check_facts(CASES) if not r.ok]
    assert not bad, "\n".join(f"{r.case} {r.fact}: golden {r.expected!r}, data {r.actual!r}" for r in bad)
