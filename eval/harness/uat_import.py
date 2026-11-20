"""Log the hosted app's live use to MLflow, beside the golden-set runs, as the separate experiment pharmagentics-uat.

Reads a downloaded copy of the state bucket (`deploy/gcp.py uat` fetches events/, jobs/ and feedback/ first).
One run per import, with the same aggregates the app's Evaluation page shows.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import mlflow

from .paths import REPO_ROOT, tracking_uri

EXPERIMENT = "pharmagentics-uat"
DEFAULT_DIR = REPO_ROOT / "local" / "uat-export"


def _flatten(prefix: str, value, out: dict[str, float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        out[prefix] = float(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, out)


def metrics(usage: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in ("excluded_test_records", "sessions", "sus", "cloud_seconds"):
        _flatten(key, usage.get(key), out)
    for lane, data in usage["lanes"].items():
        _flatten(lane, {k: v for k, v in data.items() if k != "weekly"}, out)
    return {k.replace(" ", "_"): v for k, v in out.items()}


def run(state_dir: Path = DEFAULT_DIR, uri: str | None = None) -> str | None:
    from pharmagentics.api import store, telemetry

    if not state_dir.is_dir():
        return None
    usage = telemetry.load_usage(store.LocalBackend(state_dir))
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    mlflow.set_tracking_uri(uri or tracking_uri())
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=f"uat · {(usage['since'] or 'none')[:10]} onward") as r:
        mlflow.set_tags({"suite": "uat", "source": str(state_dir.name), "since": usage["since"] or ""})
        mlflow.log_metrics(metrics(usage))
        for lane, data in usage["lanes"].items():
            for step, (week, n) in enumerate(data["weekly"].items()):
                mlflow.log_metric(f"{lane}.weekly_requests", n, step=step)
        mlflow.log_dict(usage, "usage.json")
    return r.info.run_id


if __name__ == "__main__":
    rid = run(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR)
    print(json.dumps({"run_id": rid}))
