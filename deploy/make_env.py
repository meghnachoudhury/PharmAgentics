"""Create deploy/.env.uat with random secrets for the local stack (core-007 FR-013).

The file is git-ignored. Existing values are kept, so rerunning never changes a password.
Usage: uv run python deploy/make_env.py
"""
from __future__ import annotations

import secrets
from pathlib import Path

ENV = Path(__file__).with_name(".env.uat")
KEYS = {
    "PHARMAGENTICS_SESSION_SECRET": lambda: secrets.token_urlsafe(32),
    "PHARMAGENTICS_PSEUDONYM_KEY": lambda: secrets.token_urlsafe(32),
    "PHARMAGENTICS_OIDC_CLIENT_SECRET": lambda: secrets.token_urlsafe(32),
    "PHARMAGENTICS_WORKER_TOKEN": lambda: secrets.token_urlsafe(32),  # the local agent worker (core-007 FR-028)
    "KC_BOOTSTRAP_ADMIN_PASSWORD": lambda: secrets.token_urlsafe(18),
    "UAT_PASSWORD_BRIEFING_ANALYST": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_BRIEFING_DIRECTOR": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_FORECAST_ANALYST": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_FORECAST_MANAGER": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_MENTOR_ANALYST": lambda: secrets.token_urlsafe(12),  # the mentor, edit: Commercial Analyst (P1) + CA
    "UAT_PASSWORD_MENTOR_LEADER": lambda: secrets.token_urlsafe(12),   # the mentor, leadership: Brand Director (P3) + BM
}

# Preserve existing local credentials while moving from generic Briefing names.
RENAMED_PASSWORDS = {
    "UAT_PASSWORD_ANALYST": "UAT_PASSWORD_BRIEFING_ANALYST",
    "UAT_PASSWORD_DIRECTOR": "UAT_PASSWORD_BRIEFING_DIRECTOR",
}


def main() -> None:
    current = {}
    if ENV.is_file():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
    for old, new in RENAMED_PASSWORDS.items():
        if new not in current and old in current:
            current[new] = current[old]
        current.pop(old, None)
    added = [k for k in KEYS if k not in current]
    for k in added:
        current[k] = KEYS[k]()
    ENV.write_text("# Local UAT stack secrets (git-ignored). Made by deploy/make_env.py.\n"
                   + "".join(f"{k}={v}\n" for k, v in current.items()), encoding="utf-8")
    print(f"{ENV}: {len(added)} new value(s), {len(current) - len(added)} kept.")
    print("Sign-in accounts: uat-briefing-analyst, uat-briefing-director, uat-forecast-analyst, uat-forecast-manager;")
    print(f"passwords are the UAT_PASSWORD_* lines in {ENV.name}.")
    new_passwords = [k for k in added if k.startswith("UAT_PASSWORD_")]
    if new_passwords:  # how a teammate's passwords drift from the hosted ones: see deploy/README.md
        print(f"\nNOTE: {len(new_passwords)} new sign-in password(s) were made here. They work on YOUR local stack only.\n"
              "The hosted app uses the team's shared copy. To sign in there, take that copy instead (it replaces this file):\n"
              "  uv run python deploy/gcp.py env-pull --project pharmagentics --account <your Google account>\n"
              "Passwords made here go live only after `gcp.py env-push` and `gcp.py keycloak`, which changes them for everyone.")


if __name__ == "__main__":
    main()
