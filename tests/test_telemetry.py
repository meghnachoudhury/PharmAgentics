"""The Telemetry snapshot: lane filtering, and no answer-key fields leak into it."""
from pharmagentics.api import telemetry


def test_for_lanes_keeps_own_lane_and_cross_lane_runs():
    snap = {"latest": [{"lane": "briefing"}, {"lane": "forecast"}, {"lane": "all"}], "runs": [{"lane": "forecast"}]}
    out = telemetry.for_lanes(snap, {"briefing"})
    assert [r["lane"] for r in out["latest"]] == ["briefing", "all"] and out["runs"] == []


def test_snapshot_holds_scores_only():
    snap = telemetry.snapshot()
    allowed = {"run_id", "started", "minutes", "system", "model", "lane", "control", "cases", "reruns", "judge",
               "code_version", "data_version", "metrics", "judge_metrics"}
    for r in snap["runs"]:
        assert set(r) <= allowed
        assert all(isinstance(v, (int, float)) for v in {**r["metrics"], **r["judge_metrics"]}.values())
