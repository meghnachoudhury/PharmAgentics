"""Question reading for the Forecast lane (fcst-002 step 1): does a reader turn a question into the right period,
territory and intent? Scores the draft paraphrases in eval/labels/forecast_scopes.yaml, rules against a model."""
from __future__ import annotations

import json
import time
from datetime import date

import mlflow
import yaml

from .paths import REPO_ROOT
from .systems import _lane_package

LABELS = REPO_ROOT / "eval" / "labels" / "forecast_scopes.yaml"
FIRST = "2024-10-14"


def _near(a: str, b: str) -> bool:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= 7


def check(probe: dict, weeks: list[str], territory: str, intent: str) -> dict:
    want = [str(w) for w in probe["weeks"]]
    period = bool(weeks) and _near(weeks[0], want[0]) and _near(weeks[-1], want[1])
    return {"period": period, "territory": territory == probe["territory"], "intent": intent in probe["intent"]}


def run(reader: str, model: str | None = None) -> str:
    _lane_package("forecast-explanation", "forecast_agent")
    from forecast_agent.reader import read_scope
    from forecast_agent.scope import parse_scope

    from .run import configure

    labels = yaml.safe_load(LABELS.read_text(encoding="utf-8"))
    latest = str(labels["latest"])
    configure(experiment="pharmagentics-forecast-scopes")
    rows = []
    with mlflow.start_run(run_name=f"scope reader · {reader}") as active:
        mlflow.log_params({"reader": reader, "model": model or "none", "labels": labels["status"]})
        for p in labels["probes"]:
            t = time.time()
            if reader == "model":
                s, by = read_scope(p["q"], FIRST, latest, model)
            else:
                s, by = parse_scope(p["q"], FIRST, latest), "rules"
            ok = check(p, s.weeks, s.territory, s.intent)
            rows.append({"q": p["q"], "got": [s.weeks[0] if s.weeks else None, s.weeks[-1] if s.weeks else None, s.territory, s.intent],
                         "want": [str(p["weeks"][0]), str(p["weeks"][1]), p["territory"], p["intent"]], "by": by,
                         "seconds": round(time.time() - t, 1), **ok})
        n = len(rows)
        metrics = {f"{k}_accuracy": round(sum(r[k] for r in rows) / n, 3) for k in ("period", "territory", "intent")}
        metrics["all_correct"] = round(sum(r["period"] and r["territory"] and r["intent"] for r in rows) / n, 3)
        metrics["fell_back_to_rules"] = sum(r["by"] == "rules" for r in rows) if reader == "model" else 0
        metrics["mean_seconds"] = round(sum(r["seconds"] for r in rows) / n, 1)
        mlflow.log_metrics(metrics)
        mlflow.log_text(json.dumps(rows, indent=1), "probes.json")
    print(f"Run {active.info.run_id} (scope reader: {reader}{' ' + model if model else ''}, {n} questions, labels draft)")
    for k, v in metrics.items():
        print(f"  {k:<20} {v}")
    for r in rows:
        if not (r["period"] and r["territory"] and r["intent"]):
            print(f"  MISS {r['q'][:70]:<70} got {r['got']} want {r['want']}")
    return active.info.run_id
