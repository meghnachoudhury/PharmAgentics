"""core-009 data classification, version 1: labels only, every tab classified, no change to access."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pharmagentics.api import classification, rbac
from pharmagentics.api.app import app

APP_TSX = Path(__file__).resolve().parents[1] / "frontend" / "figma-make" / "src" / "App.tsx"
C = classification.config()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PHARMAGENTICS_AUTH", "dev")
    monkeypatch.delenv("K_SERVICE", raising=False)


def signed_in(user: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/auth/dev-login", data={"username": user}, follow_redirects=False).status_code == 303
    return c


def test_levels_are_the_four_in_order():
    assert [lv["id"] for lv in C["levels"]] == ["public", "proprietary", "confidential", "sensitive"]


def test_every_role_has_a_clearance():
    assert set(C["clearance"]) == set(rbac.roles())


def test_every_tab_the_ui_shows_is_classified_and_every_key_is_used():
    used = set(re.findall(r'"((?:briefing|forecast|evaluation)\.[a-z]+(?:\.[a-z]+)?)"', APP_TSX.read_text(encoding="utf-8")))
    used |= {f"{lane}.view.{v}" for lane in ("briefing", "forecast") for v in ("analyst", "leadership")}  # built from the view name
    assert used == set(C["tabs"])


@pytest.mark.parametrize("edit", [
    lambda c: c["tabs"].update({"briefing.new": "top-secret"}),
    lambda c: c["clearance"].pop("forecast-manager"),
    lambda c: c["levels"].append(dict(c["levels"][0])),
])
def test_a_bad_edit_fails(edit):
    bad = deepcopy(C)
    edit(bad)
    with pytest.raises(ValueError):
        classification.check(bad)


def test_starting_values_mirror_todays_access():
    """Version 1 must not contradict core-007: every view a role holds is within its clearance, and no more."""
    for role in rbac.roles().values():
        for view in ("analyst", "leadership"):
            assert classification.allowed(role, f"{role.lane}.view.{view}") == (view in role.views), (role.name, view)


def test_endpoint_returns_the_callers_clearance_per_lane():
    c = signed_in("dev-tester")
    assert c.post("/api/me/view-as", json={"view": "leadership"}).status_code == 200
    body = c.get("/api/classification")
    assert body.status_code == 200 and body.headers["cache-control"] == "no-store"
    data = body.json()
    assert data["clearance"] == {"briefing": "proprietary", "forecast": "proprietary"}
    assert data["tabs"] == C["tabs"] and json.dumps(data["levels"]) == json.dumps(C["levels"])


def test_endpoint_needs_a_signed_in_role():
    assert TestClient(app).get("/api/classification").status_code == 401
    assert signed_in("dev-norole").get("/api/classification").status_code == 403
