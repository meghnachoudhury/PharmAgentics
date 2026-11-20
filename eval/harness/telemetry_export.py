"""Export an aggregate snapshot of the golden-set runs for the hosted app's Telemetry view.

The image never holds eval/ or the MLflow store (.dockerignore), so the cloud app reads this snapshot instead:
src/pharmagentics/api/telemetry.json. It holds run-level scores only: no case text, no answers, no golden facts.
`deploy/gcp.py telemetry` (run by every `gcp.py app`) uploads a fresh copy to the state bucket, which the app prefers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

from .paths import EXPERIMENT, tracking_uri

OUT = Path(__file__).resolve().parents[2] / "src" / "pharmagentics" / "api" / "telemetry.json"
JUDGE_HINTS = ("judge", "ragas", "faithfulness", "relevan")  # LLM judges are report-only (Evaluation Pack item 2)
CONTROLS = {"reference", "naive_llm"}
MAX_RUNS = 60


def _run(r) -> dict:
    p, t = r.data.params, r.data.tags
    metrics = {k.removesuffix("/mean"): round(v, 4) for k, v in sorted(r.data.metrics.items()) if k.endswith("/mean")}
    system = t.get("system", p.get("system", "?"))
    return {
        "run_id": r.info.run_id[:8],
        "started": datetime.fromtimestamp(r.info.start_time / 1000, timezone.utc).isoformat(timespec="minutes"),
        "minutes": round((r.info.end_time - r.info.start_time) / 60000, 1) if r.info.end_time else None,
        "system": system, "model": p.get("system", system).partition(":")[2] or None,
        "lane": t.get("lane", p.get("lane", "all")), "control": system in CONTROLS,
        "cases": int(p.get("cases", 0) or 0), "reruns": int(p.get("reruns", 1) or 1), "judge": p.get("judge", "off"),
        "code_version": p.get("code_version", "")[:12], "data_version": p.get("data_version", "")[:12],
        "metrics": {k: v for k, v in metrics.items() if not any(h in k.lower() for h in JUDGE_HINTS)},
        "judge_metrics": {k: v for k, v in metrics.items() if any(h in k.lower() for h in JUDGE_HINTS)},
    }


def export(out: Path = OUT, uri: str | None = None) -> dict:
    mlflow.set_tracking_uri(uri or tracking_uri())
    client = MlflowClient()
    exp = client.get_experiment_by_name(EXPERIMENT)
    runs = [] if exp is None else client.search_runs(
        [exp.experiment_id], "tags.suite = 'golden' and attributes.status = 'FINISHED'",
        order_by=["attributes.start_time DESC"], max_results=500)
    parents = [_run(r) for r in runs if "mlflow.parentRunId" not in r.data.tags][:MAX_RUNS]
    latest: dict[str, dict] = {}
    for r in parents:  # newest first, so the first per (system, lane) is the latest
        latest.setdefault(f"{r['system']}|{r['lane']}", r)
    snap = {"exported": datetime.now(timezone.utc).isoformat(timespec="minutes"), "source": "golden set (MLflow)",
            "note": "Run-level scores only. Judge scores are report-only until judge agreement clears the bar.",
            "latest": list(latest.values()), "runs": parents}
    out.write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    return snap


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    s = export(target)
    print(f"Wrote {target} ({len(s['runs'])} runs, {len(s['latest'])} system/lane pairs)")
