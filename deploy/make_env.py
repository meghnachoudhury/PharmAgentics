"""Create deploy/.env.uat with random service secrets and shared demo logins (core-007 FR-013).

The file is git-ignored. Existing values are kept, so rerunning never changes a password.
Usage: uv run python deploy/make_env.py
"""
from __future__ import annotations

import secrets
from pathlib import Path

ENV = Path(__file__).with_name(".env.uat")
DEMO_CREDENTIALS = Path(__file__).with_name("demo-credentials.env")


def demo_passwords() -> dict[str, str]:
    """Read the intentionally tracked, toy-project-only UAT login passwords."""
    values = {}
    for line in DEMO_CREDENTIALS.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {"UAT_PASSWORD_BRIEFING_ANALYST", "UAT_PASSWORD_BRIEFING_DIRECTOR",
                "UAT_PASSWORD_FORECAST_ANALYST", "UAT_PASSWORD_FORECAST_MANAGER"}
    missing = sorted(required - set(values))
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
    # "UAT_PASSWORD_BRIEFING_ANALYST": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_BRIEFING_ANALYST": lambda: DEMO_PASSWORDS["UAT_PASSWORD_BRIEFING_ANALYST"],
    # "UAT_PASSWORD_BRIEFING_DIRECTOR": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_BRIEFING_DIRECTOR": lambda: DEMO_PASSWORDS["UAT_PASSWORD_BRIEFING_DIRECTOR"],
    # "UAT_PASSWORD_FORECAST_ANALYST": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_FORECAST_ANALYST": lambda: DEMO_PASSWORDS["UAT_PASSWORD_FORECAST_ANALYST"],
    # "UAT_PASSWORD_FORECAST_MANAGER": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_FORECAST_MANAGER": lambda: DEMO_PASSWORDS["UAT_PASSWORD_FORECAST_MANAGER"],
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
    print(f"the four named UAT passwords come from {DEMO_CREDENTIALS.name}; other values are local secrets.")


if __name__ == "__main__":
    main()
