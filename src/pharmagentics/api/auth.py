"""Sign-in (core-007 FR-011 to FR-015). The server holds the session; the browser only gets a
signed, HTTP-only cookie, so no token reaches the frontend code.

PHARMAGENTICS_AUTH selects the mode:
- "oidc" (default): authorization-code flow with PKCE against Keycloak. Needs
  PHARMAGENTICS_OIDC_ISSUER (the public realm URL), PHARMAGENTICS_OIDC_CLIENT_ID and
  PHARMAGENTICS_OIDC_CLIENT_SECRET. PHARMAGENTICS_OIDC_METADATA_URL optionally points at an
  internal address for the discovery document (docker-compose: http://keycloak:8080/...).
- "dev": stand-in identities, one per role, for local work and tests. Refused on Cloud Run.
"""
from __future__ import annotations

import html
import logging
import os
from urllib.parse import urlencode
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import rbac

router = APIRouter()
logger = logging.getLogger(__name__)

DEV_USERS = {
    "dev-analyst": ("Dev Commercial Analyst", ["briefing-analyst"]),
    "dev-director": ("Dev Brand Director", ["briefing-director"]),
    "dev-forecast-analyst": ("Dev Commercial Analytics Analyst", ["forecast-analyst"]),
    "dev-forecast-manager": ("Dev Brand Manager", ["forecast-manager"]),
    "dev-norole": ("Dev user with no role", []),
}


def mode() -> str:
    m = os.environ.get("PHARMAGENTICS_AUTH", "oidc")
    if m == "dev" and os.environ.get("K_SERVICE"):
        raise RuntimeError("PHARMAGENTICS_AUTH=dev is refused on Cloud Run; use oidc.")
    return m


_oauth = None


def _client():
    global _oauth
    if _oauth is None:
        from authlib.integrations.starlette_client import OAuth

        issuer = os.environ.get("PHARMAGENTICS_OIDC_ISSUER", "").rstrip("/")
        client_id = os.environ.get("PHARMAGENTICS_OIDC_CLIENT_ID")
        secret = os.environ.get("PHARMAGENTICS_OIDC_CLIENT_SECRET")
        if not (issuer and client_id and secret):
            raise HTTPException(status_code=503, detail="Sign-in is not configured on this server.")
        oauth = OAuth()
        oauth.register(
            "keycloak", client_id=client_id, client_secret=secret,
            server_metadata_url=os.environ.get("PHARMAGENTICS_OIDC_METADATA_URL")
            or f"{issuer}/.well-known/openid-configuration",
            # Keycloak scales to zero and needs about 16 s to start (core-007 SC-004 allows 60 s with a cold start),
            # so wait longer than httpx's default of 5 s.
            client_kwargs={"scope": "openid profile", "code_challenge_method": "S256", "timeout": 50.0},
        )
        _oauth = oauth
    return _oauth.keycloak


def _set_user(request: Request, sub: str, name: str, roles: list[str]) -> None:
    known = set(rbac.roles())
    request.session.clear()
    request.session["user"] = {"sub": sub, "name": name, "roles": [r for r in roles if r in known]}


@router.get("/auth/login", include_in_schema=False)
async def login(request: Request):
    if mode() == "dev":
        buttons = "".join(
            f'<button name="username" value="{html.escape(u)}">{html.escape(n)}'
            f'<small>{html.escape(", ".join(r) or "no role")}</small></button>'
            for u, (n, r) in DEV_USERS.items())
        return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Development sign-in</title>
<style>body{{font-family:system-ui,sans-serif;background:#f7f4ee;color:#1b2433;margin:0;padding:48px 16px}}
main{{max-width:420px;margin:auto}}p{{color:#5b6472;font-size:14px}}button{{display:block;width:100%;margin:8px 0;padding:14px;
border:1px solid #ddd5c6;border-radius:12px;background:#fff;text-align:left;font-size:15px;cursor:pointer}}
small{{display:block;color:#5b6472;margin-top:2px}}</style></head><body><main><h1>Development sign-in</h1>
<p>Stand-in identities for local work. The deployed app signs in through Keycloak instead.</p>
<form method="post" action="/auth/dev-login">{buttons}</form></main></body></html>""")
    redirect_uri = str(request.url_for("auth_callback"))
    client = _client()  # a 503 here means sign-in is not configured, which is not a cold start
    try:
        return await client.authorize_redirect(request, redirect_uri)
    except Exception:  # noqa: BLE001 - any failure to reach Keycloak (timeouts, refused connections; the transport's types vary)
        logger.warning("Sign-in service unreachable; showing the retry page", exc_info=True)
        return _starting_page()


def _starting_page() -> HTMLResponse:
    """The sign-in service did not answer in time (a cold start that ran long): retry instead of a bare 500."""
    return HTMLResponse("""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="5">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Starting sign-in</title>
<style>body{font-family:system-ui,sans-serif;background:#f7f4ee;color:#1b2433;display:grid;place-items:center;height:100vh;margin:0;padding:0 16px}
p{color:#5b6472}</style></head><body><main><h1>Starting the sign-in service</h1>
<p>It sleeps when nobody is using it and takes a few seconds to wake. This page retries by itself.</p></main></body></html>""",
                        status_code=503, headers={"Retry-After": "5", "Cache-Control": "no-store"})


@router.post("/auth/dev-login", include_in_schema=False)
async def dev_login(request: Request, username: str = Form(...)):
    if mode() != "dev" or username not in DEV_USERS:
        raise HTTPException(status_code=404)
    name, roles = DEV_USERS[username]
    _set_user(request, username, name, roles)
    return RedirectResponse("/", status_code=303)


@router.get("/auth/callback", name="auth_callback", include_in_schema=False)
async def callback(request: Request):
    if mode() != "oidc":
        raise HTTPException(status_code=404)
    token = await _client().authorize_access_token(request)  # validates the ID token (issuer, audience, signature, nonce)
    claims = token.get("userinfo") or {}
    _set_user(request, claims["sub"], claims.get("name") or claims.get("preferred_username", ""), list(claims.get("roles", [])))
    request.session["id_token"] = token.get("id_token")
    return RedirectResponse("/", status_code=303)


@router.get("/auth/logout", include_in_schema=False)
async def logout(request: Request):
    id_token = request.session.get("id_token")
    request.session.clear()
    if mode() != "oidc":
        return RedirectResponse("/", status_code=303)
    client = _client()
    metadata = await client.load_server_metadata()
    params = {"post_logout_redirect_uri": str(request.base_url), "client_id": client.client_id}
    if id_token:
        params["id_token_hint"] = id_token
    return RedirectResponse(f"{metadata['end_session_endpoint']}?{urlencode(params)}", status_code=303)
