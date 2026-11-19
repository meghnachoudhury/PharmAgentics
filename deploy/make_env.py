"""Create deploy/.env.uat with random service secrets and the shared demo logins (core-007 FR-013).

The file is git-ignored because it holds service secrets. The six shared sign-in passwords come from
the tracked deploy/demo-credentials.env and always replace what the file had, so every clone signs in
with the same passwords. Every other existing value is kept, so rerunning never changes a secret.
Usage: uv run python deploy/make_env.py
"""
from __future__ import annotations

import secrets
from pathlib import Path

ENV = Path(__file__).with_name(".env.uat")
DEMO_CREDENTIALS = Path(__file__).with_name("demo-credentials.env")

# Sign-in account -> its password line in demo-credentials.env.
DEMO_ACCOUNTS = {
    "uat-briefing-analyst": "UAT_PASSWORD_BRIEFING_ANALYST",
    "uat-briefing-director": "UAT_PASSWORD_BRIEFING_DIRECTOR",
    "uat-forecast-analyst": "UAT_PASSWORD_FORECAST_ANALYST",
    "uat-forecast-manager": "UAT_PASSWORD_FORECAST_MANAGER",
    "uat-both-analyst": "UAT_PASSWORD_BOTH_ANALYST",  # both lanes: Commercial Analyst (P1) + CA, like dev-both-analyst
    "uat-both-leader": "UAT_PASSWORD_BOTH_LEADER",    # both lanes: Brand Director (P3) + BM, like dev-both-leader
}


def demo_passwords() -> dict[str, str]:
    """Read the intentionally tracked, toy-project-only UAT login passwords."""
    values = {}
    for line in DEMO_CREDENTIALS.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    missing = sorted(k for k in DEMO_ACCOUNTS.values() if not values.get(k))
    if missing:
        raise RuntimeError(f"{DEMO_CREDENTIALS} is missing: {', '.join(missing)}")
    return values


DEMO_PASSWORDS = demo_passwords()

KEYS = {
    "PHARMAGENTICS_SESSION_SECRET": lambda: secrets.token_urlsafe(32),
    "PHARMAGENTICS_PSEUDONYM_KEY": lambda: secrets.token_urlsafe(32),
    "PHARMAGENTICS_OIDC_CLIENT_SECRET": lambda: secrets.token_urlsafe(32),
    "PHARMAGENTICS_WORKER_TOKEN": lambda: secrets.token_urlsafe(32),  # the local agent worker (core-007 FR-028)
    "KC_BOOTSTRAP_ADMIN_PASSWORD": lambda: secrets.token_urlsafe(18),
    "UAT_PASSWORD_MENTOR_ANALYST": lambda: secrets.token_urlsafe(12),  # the mentor, edit: Commercial Analyst (P1) + CA
    "UAT_PASSWORD_MENTOR_LEADER": lambda: secrets.token_urlsafe(12),   # the mentor, leadership: Brand Director (P3) + BM
}

# Old names in local files from before the lane split; the shared passwords replace their values.
OLD_NAMES = ["UAT_PASSWORD_ANALYST", "UAT_PASSWORD_DIRECTOR"]


def main() -> None:
    current = {}
    if ENV.is_file():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
    for old in OLD_NAMES:
        current.pop(old, None)
    shared = {k: DEMO_PASSWORDS[k] for k in DEMO_ACCOUNTS.values()}
    changed = [k for k, v in shared.items() if current.get(k) != v]
    current.update(shared)
    added = [k for k in KEYS if k not in current]
    for k in added:
        current[k] = KEYS[k]()
    ENV.write_text("# Local UAT stack secrets (git-ignored). Made by deploy/make_env.py.\n"
                   + "".join(f"{k}={v}\n" for k, v in current.items()), encoding="utf-8")
    print(f"{ENV}: {len(added)} new secret(s), {len(changed)} shared sign-in password(s) set from {DEMO_CREDENTIALS.name}.")
    print("Shared sign-ins (passwords in deploy/demo-credentials.env):")
    for account, key in DEMO_ACCOUNTS.items():
        print(f"  {account:<22} {DEMO_PASSWORDS[key]}")
    new_passwords = [k for k in added if k.startswith("UAT_PASSWORD_")]
    if new_passwords:  # how a teammate's passwords drift from the hosted ones: see deploy/README.md
        print(f"\nNOTE: {len(new_passwords)} new mentor sign-in password(s) were made here. They work on YOUR local stack only.\n"
              "The hosted app uses the team's shared copy. To sign in there, take that copy instead (it replaces this file):\n"
              "  uv run python deploy/gcp.py env-pull --project pharmagentics --account <your Google account>\n"
              "Passwords made here go live only after `gcp.py env-push` and `gcp.py keycloak`, which changes them for everyone.")


if __name__ == "__main__":
    main()
