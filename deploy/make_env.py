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
    "KC_BOOTSTRAP_ADMIN_PASSWORD": lambda: secrets.token_urlsafe(18),
    "UAT_PASSWORD_ANALYST": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_DIRECTOR": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_FORECAST_ANALYST": lambda: secrets.token_urlsafe(12),
    "UAT_PASSWORD_FORECAST_MANAGER": lambda: secrets.token_urlsafe(12),
}


def main() -> None:
    current = {}
    if ENV.is_file():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
    added = [k for k in KEYS if k not in current]
    for k in added:
        current[k] = KEYS[k]()
    ENV.write_text("# Local UAT stack secrets (git-ignored). Made by deploy/make_env.py.\n"
                   + "".join(f"{k}={v}\n" for k, v in current.items()), encoding="utf-8")
    print(f"{ENV}: {len(added)} new value(s), {len(current) - len(added)} kept.")
    print("Sign-in accounts: uat-analyst, uat-director, uat-forecast-analyst, uat-forecast-manager;")
    print(f"passwords are the UAT_PASSWORD_* lines in {ENV.name}.")


if __name__ == "__main__":
    main()
