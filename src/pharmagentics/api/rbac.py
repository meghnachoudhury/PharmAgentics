"""Role-based access (core-007). The server decides every view from the signed-in role.

The policy lives in roles.json. A signed-in user is a Principal kept in the signed
session cookie (see auth.py); its role names come from Keycloak realm roles, or from
the stand-in identities in development mode.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request

POLICY_FILE = Path(__file__).with_name("roles.json")
ANALYST, LEADERSHIP = "analyst", "leadership"


@dataclass(frozen=True)
class Role:
    name: str
    lane: str
    persona: str
    label: str
    views: tuple[str, ...]
    actions: tuple[str, ...]


@lru_cache(maxsize=1)
def policy() -> dict:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def roles() -> dict[str, Role]:
    return {name: Role(name, r["lane"], r["persona"], r["label"], tuple(r["views"]), tuple(r["actions"]))
            for name, r in policy()["roles"].items()}


def lane_available(lane: str) -> bool:
    return bool(policy()["lanes"].get(lane, {}).get("available"))


@dataclass(frozen=True)
class Principal:
    sub: str
    name: str
    role_names: tuple[str, ...]

    def role(self, lane: str) -> Role | None:
        """The user's role in a lane. Roles not in the policy are ignored; if a user holds two roles
        in one lane by mistake, the more restricted one (fewer views) applies."""
        known = [r for n, r in roles().items() if n in self.role_names and r.lane == lane]
        return min(known, key=lambda r: (len(r.views), r.name)) if known else None

    @property
    def lanes(self) -> list[Role]:
        return [r for lane in ("briefing", "forecast") if (r := self.role(lane))]


def principal(request: Request) -> Principal | None:
    user = request.session.get("user")
    if not user:
        return None
    return Principal(user["sub"], user.get("name", ""), tuple(user.get("roles", [])))


def require_user(request: Request) -> Principal:
    p = principal(request)
    if p is None:
        raise HTTPException(status_code=401, detail="Sign in first.")
    return p


def require_briefing(request: Request) -> tuple[Principal, Role]:
    p = require_user(request)
    role = p.role("briefing")
    if role is None:
        raise HTTPException(status_code=403, detail="Your account has no Briefing role.")
    return p, role


def allow(role: Role, action: str) -> None:
    if action not in role.actions:
        raise HTTPException(status_code=403, detail=f"The {role.label} role cannot {action}.")


def view_for(role: Role, requested: str | None) -> str:
    """Default to the role's first view; refuse a view the role does not hold (FR-004)."""
    if requested is None:
        return role.views[0]
    if requested not in role.views:
        raise HTTPException(status_code=403, detail=f"The {role.label} role cannot open the {requested} view.")
    return requested


def pseudonym(sub: str) -> str:
    """Stable participant ID for UAT events; never the name or email (FR-025)."""
    key = (os.environ.get("PHARMAGENTICS_PSEUDONYM_KEY") or os.environ.get("PHARMAGENTICS_SESSION_SECRET") or "dev").encode()
    return "u-" + hmac.new(key, sub.encode(), hashlib.sha256).hexdigest()[:12]
