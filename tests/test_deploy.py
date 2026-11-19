"""core-007 deployment guards that run without Google Cloud."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gcp", ROOT / "deploy" / "gcp.py")
gcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gcp)

ENV = {"PHARMAGENTICS_OIDC_CLIENT_SECRET": "s3cret", "UAT_PASSWORD_BRIEFING_ANALYST": "a", "UAT_PASSWORD_BRIEFING_DIRECTOR": "d",
       "UAT_PASSWORD_FORECAST_ANALYST": "fa", "UAT_PASSWORD_FORECAST_MANAGER": "fm",
       "UAT_PASSWORD_TESTER": "t"}


def test_realm_in_repo_holds_no_secret_values():
    realm = json.loads((ROOT / "deploy" / "keycloak" / "realm-pharmagentics.json").read_text(encoding="utf-8"))
    client = realm["clients"][0]
    assert client["secret"] == "${PHARMAGENTICS_OIDC_CLIENT_SECRET}"
    for user in realm["users"]:
        assert all(c["value"].startswith("${UAT_PASSWORD_") for c in user["credentials"])
    assert realm["registrationAllowed"] is False  # FR-012: no self-registration


SHARED_LOGINS = {"uat-briefing-analyst": "UAT_PASSWORD_BRIEFING_ANALYST", "uat-briefing-director": "UAT_PASSWORD_BRIEFING_DIRECTOR",
                 "uat-forecast-analyst": "UAT_PASSWORD_FORECAST_ANALYST", "uat-forecast-manager": "UAT_PASSWORD_FORECAST_MANAGER",
                 "uat-tester": "UAT_PASSWORD_TESTER"}


def test_versioned_demo_credentials_contain_only_the_shared_uat_passwords():
    values = {}
    for line in (ROOT / "deploy" / "demo-credentials.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    assert set(values) == set(SHARED_LOGINS.values())  # never a service secret
    assert all(values.values())


def test_each_shared_password_belongs_to_its_realm_account():
    realm = json.loads((ROOT / "deploy" / "keycloak" / "realm-pharmagentics.json").read_text(encoding="utf-8"))
    users = {u["username"]: u for u in realm["users"]}
    for account, key in SHARED_LOGINS.items():
        assert users[account]["credentials"][0]["value"] == "${" + key + "}"


def test_the_realm_has_exactly_the_five_logins_and_the_tester_holds_only_the_test_role():
    realm = json.loads((ROOT / "deploy" / "keycloak" / "realm-pharmagentics.json").read_text(encoding="utf-8"))
    users = {u["username"]: u for u in realm["users"]}
    assert set(users) == set(SHARED_LOGINS)
    assert users["uat-tester"]["realmRoles"] == ["tester"]


def test_realm_roles_match_the_policy():
    realm = json.loads((ROOT / "deploy" / "keycloak" / "realm-pharmagentics.json").read_text(encoding="utf-8"))
    policy = json.loads((ROOT / "src" / "pharmagentics" / "api" / "roles.json").read_text(encoding="utf-8"))
    assert {r["name"] for r in realm["roles"]["realm"]} == set(policy["roles"]) | {policy["test_role"]["name"]}


def test_render_realm_fills_every_placeholder():
    text = gcp.render_realm(ENV, "https://app.example")
    assert "${" not in text
    realm = json.loads(text)
    assert realm["clients"][0]["redirectUris"] == ["https://app.example/auth/callback"]


def test_render_realm_refuses_a_missing_password():
    with pytest.raises(SystemExit, match="UAT_PASSWORD_BRIEFING_DIRECTOR"):
        gcp.render_realm({k: v for k, v in ENV.items() if k != "UAT_PASSWORD_BRIEFING_DIRECTOR"}, "https://app.example")


def test_dockerignore_is_an_allow_list_that_keeps_eval_out():
    lines = [l.strip() for l in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    assert lines[0] == "*"
    assert not any(l.startswith("!") and ("eval" in l or "SoT" in l or ".env" in l) for l in lines)


def test_failed_event_write_does_not_stop_the_briefing(monkeypatch, tmp_path):
    from pharmagentics.api import store

    class Broken:
        def write(self, key, text):
            raise OSError("bucket unreachable")

    with patch.object(store, "backend", return_value=Broken()):
        store.record_event("requested", user="u-x")  # must not raise
