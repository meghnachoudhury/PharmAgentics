"""Real (not mocked) API → Briefing baseline → governed DuckDB integration.

Skipped until the synthetic database is loaded. GitHub Actions loads the
release first so the CI job must run this test rather than skip it.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api.app import app
from pharmagentics.api import service


@pytest.mark.skipif(not service.DB.is_file(), reason="Build local/pharmagentics.duckdb first")
def test_real_weekly_briefing_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    client = TestClient(app)
    client.post("/auth/dev-login", data={"username": "dev-analyst"})
    response = client.post("/api/briefing/query", json={
        "intent": "weekly_brief",
        "brand_id": "BXA",
        "territory_id": "PACIFIC",
        "week_start": "2026-06-08",
        "question": "What changed this week?",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["system"] == "briefing_scripted"
    assert body["status"] == "draft_requires_review"
    assert body["review_status"] == "pending"  # stored for the analyst's review (core-007)
    assert "2026-06-08" in body["answer"]
    assert body["claims"] and body["evidence"]
    evidence = {item["id"]: item for item in body["evidence"]}
    assert body["data_version"] not in (None, "unavailable")
    for claim in body["claims"]:
        assert claim["evidence_id"] in evidence
        assert evidence[claim["evidence_id"]]["data_version"] == body["data_version"]
    # Running a brief never approves it; only the analyst's review does (core-007 FR-009).
    assert body["review_status"] == "pending"
