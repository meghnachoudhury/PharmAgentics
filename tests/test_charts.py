"""brief-003 slice 2: charts built from governed rows (FR-024), the data behind each section (FR-025) and the
leadership cut (FR-026). Real scripted engine; no model."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents" / "brand-briefing"))

from pharmagentics.api.views import leadership_sections  # noqa: E402
from pharmagentics.tools import DEFAULT_DB  # noqa: E402

needs_db = pytest.mark.skipif(not DEFAULT_DB.exists(), reason="build it with: uv run python src/pharmagentics/data/load_duckdb.py")
PACIFIC_JUNE = "Weeks of 2026-06-01 to 2026-06-29, Pacific: Why did BXA prescriptions fall?"
NEW_ENGLAND = "Week of 2026-05-04 in New England: Generate the weekly brand-performance briefing."


def brief(question: str) -> dict:
    from briefing_baseline import answer

    return answer(question)


def by_number(env: dict) -> dict[str, dict]:
    return {s["number"]: s for s in env["sections"]}


def tables(section: dict) -> list[dict]:
    chart = section.get("chart") or {}
    return [t for t in (chart.get("table"), (chart.get("panel") or {}).get("table")) if t]


@needs_db
def test_every_chart_table_reruns_to_the_rows_it_shows():
    """FR-025: each plotted point comes from a query an analyst can re-run and get the same rows."""
    env = brief(PACIFIC_JUNE)
    evidence = {e["id"]: e for e in env["evidence"]}
    found = 0
    with duckdb.connect(str(DEFAULT_DB), read_only=True) as con:
        for s in env["sections"]:
            for t in tables(s):
                found += 1
                assert evidence[t["evidence_id"]]["query"] == t["query"]
                rows = [[(round(float(v), 4) if isinstance(v, float) else v) for v in r] for r in con.execute(t["query"]).fetchall()]
                assert json.loads(json.dumps(rows, default=str)) == json.loads(json.dumps(t["rows"], default=str))
    assert found >= 4  # §2 trend, §3.1 story and its driver panel, §4 coverage


@needs_db
def test_the_memo_carries_the_three_chart_kinds():
    sections = by_number(brief(PACIFIC_JUNE))
    assert sections["2"]["chart"]["kind"] == "trend" and len(sections["2"]["chart"]["weeks"]) == 13
    story = sections["3.1"]["chart"]
    assert story["kind"] == "story" and story["band"]["low"] <= story["band"]["high"]
    assert story["panel"]["driver"] == "supply"  # the June Pacific supply shortfall
    assert sections["4"]["chart"]["kind"] == "coverage"


@needs_db
def test_a_projected_week_is_hollow_and_called_an_assumption():
    chart = by_number(brief(NEW_ENGLAND))["2"]["chart"]
    national = chart["series"][0]["points"][-1]
    territory = chart["series"][1]["points"][-1]
    assert national["basis"] == "projected" and territory["basis"] == "projected"
    assert "an assumption" in chart["caption"]
    cells = [c for r in by_number(brief(NEW_ENGLAND))["4"]["chart"]["rows"] if r["territory"] == "New England" for c in r["cells"]]
    assert cells[-1]["basis"] == "projected"


@needs_db
def test_captions_and_explanations_are_in_the_answer_and_traced():
    """FR-027: the flattened answer carries every caption and explanation, so the gated scorers check them."""
    env = brief(PACIFIC_JUNE)
    for s in env["sections"]:
        if s.get("chart"):
            assert s["chart"]["caption"] in env["answer"] and s["chart"]["explanation"] in env["answer"]
    assert "below its baseline band" in by_number(env)["3.1"]["chart"]["explanation"]


@needs_db
def test_leaders_get_charts_without_tables_queries_claims_or_checks():
    sections = leadership_sections(brief(PACIFIC_JUNE)["sections"])
    assert [s["number"] for s in sections][:3] == ["1", "2", "3"] and sections[-1]["number"] == "5"
    assert not any(s["number"].startswith(("4", "6")) for s in sections)
    text = json.dumps(sections)
    for leak in ("select ", "evidence_id", "\"claims\"", "citations", "\"table\"", "Checked, in this order"):
        assert leak not in text, leak
    story = next(s for s in sections if s["number"] == "3.1")
    assert story["chart"]["panel"]["points"] and story["chart"]["band"]
