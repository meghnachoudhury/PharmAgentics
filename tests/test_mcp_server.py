"""The PharmAgentics MCP server: same numbers as the shared stage code, tokens only, governed inputs."""
from __future__ import annotations

import asyncio
import inspect
import json
import re

import pytest
from mcp.client.client import Client

from pharmagentics.mcp_server import ADMIN_TOOLS, AGENT_TOOLS, RunSession, build_server
from pharmagentics.tools import DEFAULT_DB, Registry, stages
from pharmagentics.tools.registry import digits_outside_tokens

pytestmark = pytest.mark.skipif(not DEFAULT_DB.exists(), reason="build local/pharmagentics.duckdb first")

ARTIFACT_WEEK = "Week of 2026-04-06, today's snapshot: Is this change real, or a data or calendar artifact?"
PACIFIC = "Pacific, 2026-06-01 to 2026-06-29: why did BXA fall?"
LEGEND = "\n\nToken values"


def _body(text: str) -> str:
    return text.split(LEGEND, 1)[0]


def _call(server_calls):
    async def go():
        async with Client(build_server()) as c:
            out = []
            for name, args in server_calls:
                r = await c.call_tool(name, args)
                out.append("\n".join(getattr(x, "text", "") for x in r.content))
            return out
    return asyncio.run(go())


def test_tool_list_is_the_two_groups_plus_admin():
    async def go():
        async with Client(build_server()) as c:
            return {t.name: t for t in (await c.list_tools()).tools}
    tools = asyncio.run(go())
    expected = set(ADMIN_TOOLS) | {t for group in AGENT_TOOLS.values() for t in group}
    assert set(tools) == expected
    # No tool takes free text the agent could turn into SQL: only a territory, or nothing (FR-020).
    for name in expected - set(ADMIN_TOOLS):
        assert set(tools[name].input_schema.get("properties", {})) <= {"territory"}, name


def test_numbers_are_tokens_and_match_the_shared_stage_code():
    s = RunSession(legend=True)
    try:
        s.open_run(ARTIFACT_WEEK)
        kpis = s.national_kpis()
        assert not digits_outside_tokens(_body(kpis)), kpis
        values = dict(re.findall(r"\{(c\d+)\} = ([^;]+)", kpis.split(LEGEND, 1)[1]))
        reg = Registry()
        try:
            p = stages.resolve(reg, ARTIFACT_WEEK)
            direct = reg.render("\n".join(stages.kpis(reg, p)))
        finally:
            reg.close()
        rendered = re.sub(r"\{(c\d+)\}", lambda m: values[m.group(1)], _body(kpis))
        assert rendered == direct
    finally:
        s.close()


def test_every_agent_tool_keeps_digits_inside_tokens():
    s = RunSession()
    try:
        s.open_run(PACIFIC)
        texts = [s.feed_health(), s.restatements(), s.national_kpis(), s.screen_territories(), s.competitor_status()]
        for fn in (s.territory_change, s.check_access, s.check_promotion, s.check_supply, s.check_competitor,
                   s.check_data, s.story_confidence):
            texts.append(fn("PACIFIC"))
        for text in texts:
            assert LEGEND not in text  # off by default
            assert not digits_outside_tokens(text), text
        run = s.export_run()
        ids = {e["id"] for e in run["evidence"]}
        assert run["claims"] and all(c["evidence_id"] in ids for c in run["claims"])
        assert {e["data_version"] for e in run["evidence"]} == {s.reg.data_version}
        s.open_run("Week of 2025-01-06: what changed?")  # Metacora not launched yet: the no-story branch
        assert not digits_outside_tokens(s.competitor_status())
    finally:
        s.close()


def test_confidence_is_code_and_an_untested_driver_keeps_it_below_high():
    s = RunSession()
    try:
        s.open_run(PACIFIC)
        so_far = s.check_supply("PACIFIC")
        assert "Story so far for Pacific" in so_far and "Not tested yet" in so_far
        one = s.story_confidence("PACIFIC")
        assert "Not tested:" in one and "High" not in one
        for fn in (s.check_data, s.check_access, s.check_promotion, s.check_competitor):
            fn("PACIFIC")
        full = s.story_confidence("PACIFIC")
        assert "Not tested:" not in full
        assert s.stories["PACIFIC"]["verdicts"]["supply"] == "supported" and s.stories["PACIFIC"]["closed"]
        assert s.export_run()["abstained"] is False
    finally:
        s.close()


def test_territory_names_ids_and_bad_input():
    s = RunSession()
    try:
        s.open_run(ARTIFACT_WEEK)
        assert s.check_supply("pacific").startswith("Pacific.")
        assert s.check_supply("Mid-Atlantic").startswith("Mid-Atlantic has cuts that fail the feed gate")
        assert s.check_data("Mid-Atlantic").startswith("Mid-Atlantic. Data artifact: not ruled out")
        assert s.check_supply("Atlantis").startswith("Unknown territory")
    finally:
        s.close()


def test_tools_refuse_without_an_open_run_and_export_is_json():
    out = _call([("feed_health", {}), ("open_run", {"question": ARTIFACT_WEEK}), ("feed_health", {}), ("export_run", {})])
    assert "open_run" in out[0]
    assert "{c1}" in out[2]
    assert json.loads(out[3])["calls"] == [{"tool": "feed_health", "args": {}}]


def test_tool_functions_hold_no_model():
    """Tools are plain code (guardrail rule 1): the server module imports no model client."""
    import pharmagentics.mcp_server.server as srv
    src = inspect.getsource(srv)
    assert "agent_framework" not in src and "pharmagentics.llm" not in src and "ollama" not in src.lower()
