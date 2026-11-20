"""The analyst's brand overview: analyst-only, every headline figure traceable, territories judged by the triage rule."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import overview, service
from pharmagentics.api.app import app
from pharmagentics.tools import Registry, stages
from pharmagentics.tools import queries as q

pytestmark = pytest.mark.skipif(not service.DB.is_file(), reason="needs the DuckDB release")
JUNE = "2026-06-01"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.setenv("PHARMAGENTICS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("PHARMAGENTICS_STATE_BUCKET", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)


def signed_in(user: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303
    return c


@pytest.fixture(scope="module")
def june() -> dict:
    return overview.build(JUNE)


def test_only_analysts_can_open_it():
    r = signed_in("dev-analyst").get(f"/api/briefing/overview?week={JUNE}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert signed_in("dev-director").get("/api/briefing/overview").status_code == 403
    assert signed_in("dev-forecast-analyst").get("/api/briefing/overview").status_code == 403
    assert TestClient(app).get("/api/briefing/overview").status_code == 401


def test_week_outside_the_release_is_refused():
    assert signed_in("dev-analyst").get("/api/briefing/overview?week=1999-01-04").status_code == 400


def test_territories_are_judged_by_the_triage_rule(june):
    reg = Registry(service.DB)
    try:
        p = stages.resolve(reg, f"Week of {JUNE} in National: What changed this week?")
        found, _ = stages.screen(reg, p)
    finally:
        reg.close()
    by_status = {s: {t["id"] for t in june["territories"] if t["status"] == s} for s in ("material", "normal", "held_back")}
    assert by_status["material"] == {s["territory"] for s in found if s["kind"] == "territory"}
    assert by_status["held_back"] == set(q.TERRITORY_NAMES) - {"NATIONAL"} - set(p.ok)
    assert "PACIFIC" in by_status["material"]
    for t in june["territories"]:
        if t["status"] == "material":
            assert abs(t["change"]) >= t["threshold"] and abs(t["gap"]) >= stages.MATERIAL_GAP
        elif t["status"] == "normal":
            assert abs(t["change"]) < t["threshold"] or abs(t["gap"]) < stages.MATERIAL_GAP
    ranks = [t["status"] for t in june["territories"]]
    assert ranks == sorted(ranks, key=["material", "normal", "held_back"].index)


def test_the_first_week_has_nothing_to_compare_with():
    first = overview.build("2024-10-14")
    assert first["baseline"] == [] and {t["status"] for t in first["territories"]} == {"no_baseline"}
    assert first["stats"][0]["change"] is None


def test_every_headline_figure_reruns_to_the_same_value(june):
    evidence = {e["id"]: e for e in june["evidence"]}
    reg = Registry(service.DB)
    try:
        for s in june["stats"]:
            for claim in filter(None, [s, s["change"]]):
                e = evidence[claim["evidence_id"]]
                assert e["data_version"] == june["data_version"]
                assert float(reg.scalar(e["query"]) or 0) == pytest.approx(e["result"])
        trx = reg.scalar(q.trx_sum([JUNE]))
    finally:
        reg.close()
    assert june["stats"][0]["value"] == f"{round(trx):,}"


def test_series_and_mix_are_consistent(june):
    for t in june["territories"]:
        assert len(t["series"]) <= overview.SERIES_WEEKS and t["series"][-1]["week"] <= JUNE
        if t["trx"] is not None:
            bxa = next(m for m in t["mix"] if m["product"] == "BXA")
            assert bxa["trx"] == t["trx"]
        shares = [m["share"] for m in t["mix"] if m["share"] is not None]
        assert not shares or sum(shares) == pytest.approx(1.0)
        assert set(t["evidence_ids"]) <= {e["id"] for e in june["evidence"]}
