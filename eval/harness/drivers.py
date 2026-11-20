"""Driver recovery for the Forecast lane (fcst-001): does a system accept the drivers that act in a window and
no others? Scores the draft probes in eval/labels/forecast_drivers.yaml and logs recall, false drivers and a
confusion matrix to MLflow. The harness calls the agent package; the agent never reads this."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import mlflow
import yaml

from .paths import REPO_ROOT
from .systems import _lane_package

LABELS = REPO_ROOT / "eval" / "labels" / "forecast_drivers.yaml"
# The app's driver-recovery board reads this snapshot (like telemetry.json); it holds scores, never labels' sources.
SNAPSHOT = REPO_ROOT / "src" / "pharmagentics" / "api" / "forecast_drivers.json"
DRIVERS = ["access", "promotion", "supply", "competitor", "none"]
NAMES = {"NATIONAL": "", "MID_ATLANTIC": "Mid-Atlantic", "GREAT_LAKES": "Great Lakes", "PACIFIC": "Pacific",
         "SOUTHEAST": "Southeast", "SOUTH_CENTRAL": "South Central", "MOUNTAIN": "Mountain", "NORTHWEST": "Northwest",
         "NEW_ENGLAND": "New England"}


def _mondays(a: str, b: str) -> list[str]:
    from datetime import date, timedelta

    d, end, out = date.fromisoformat(a), date.fromisoformat(b), []
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


def probes() -> list[dict]:
    return yaml.safe_load(LABELS.read_text(encoding="utf-8"))["probes"]


def question(p: dict) -> str:
    where = NAMES[p["territory"]]
    return f"Weeks of {p['weeks'][0]} to {p['weeks'][1]}{', ' + where if where else ''}: What explains the miss?"


def accepted(report: dict, territory: str) -> set[str]:
    """Drivers the answer accepts for this territory: its own local drivers and broad ones."""
    out = set()
    for d in report.get("drivers", []):
        if territory == "NATIONAL" and d["territory"] != "ALL":
            continue  # a national probe is about the broad driver; local episodes are scored in their own probes
        if d["territory"] in (territory, "ALL"):
            out.add(d["driver"])
    return out


def score(rows: list[dict]) -> dict:
    """Recall over expected drivers, false drivers, exact-set accuracy and a multi-label confusion matrix."""
    cm = {t: Counter() for t in DRIVERS}
    hit = expected = false = exact = 0
    for r in rows:
        e, p = set(r["expect"]), set(r["got"])
        expected += len(e)
        hit += len(e & p)
        false += len(p - e)
        exact += e == p
        for d in e:
            if d in p:
                cm[d][d] += 1
            elif p - e:
                for q in p - e:
                    cm[d][q] += 1
            else:
                cm[d]["none"] += 1
        if not e:
            for q in p or {"none"}:
                cm["none"][q] += 1
    return {"metrics": {"driver_recall": round(hit / expected, 3) if expected else 1.0, "false_drivers": false,
                        "exact_set_share": round(exact / len(rows), 3), "probes": len(rows)},
            "confusion": {t: dict(cm[t]) for t in DRIVERS}}


def table(confusion: dict) -> str:
    head = "true \\ got".ljust(12) + "".join(d.rjust(12) for d in DRIVERS)
    lines = [head] + [t.ljust(12) + "".join(str(confusion[t].get(d, 0)).rjust(12) for d in DRIVERS) for t in DRIVERS]
    return "\n".join(lines)


def run(system: str, model: str | None = None) -> str:
    pkg = _lane_package("forecast-explanation", "forecast_agent")
    from .run import configure

    configure(experiment="pharmagentics-forecast-drivers")
    rows = []
    with mlflow.start_run(run_name=f"{system} · driver recovery") as active:
        mlflow.log_params({"system": system, "model": model or "none", "labels": "draft",
                           "agent_config_version": pkg.config_version()})
        for p in probes():
            # The probe's scope is given, as if confirmed on the scope card, so only the investigation differs.
            weeks = [w for w in _mondays(str(p["weeks"][0]), str(p["weeks"][1]))]
            out = pkg.answer(question(p), model=model, territory=p["territory"], weeks=weeks, intent="attribution", writer=False,
                             investigator="model" if system == "forecast_investigator" else "rules")
            rep = out.get("report") or {}
            rows.append({"id": p["id"], "question": question(p), "expect": p["expect"],
                         "got": sorted(accepted(rep, p["territory"])),
                         "rejected": [c["label"] for c in rep.get("candidates", []) if c["status"] == "rejected"],
                         "left_undecided": (out.get("trajectory") or {}).get("left_undecided"),
                         "seconds": (out.get("trajectory") or {}).get("seconds")})
        result = score(rows)
        mlflow.log_metrics(result["metrics"])
        mlflow.log_metric("left_undecided", sum(r.get("left_undecided") or 0 for r in rows))
        mlflow.log_text(table(result["confusion"]), "confusion.txt")
        mlflow.log_text(json.dumps(rows, indent=1), "probes.json")
    _export(system, model, active.info.run_id, result, rows)
    print(f"Run {active.info.run_id} ({system}, driver recovery, labels draft)")
    for k, v in result["metrics"].items():
        print(f"  {k:<20} {v}")
    print(table(result["confusion"]))
    for r in rows:
        mark = "ok " if set(r["expect"]) == set(r["got"]) else "MISS"
        print(f"  {mark} {r['id']:<24} expect {r['expect']} got {r['got']}")
    return active.info.run_id


def _export(system: str, model: str | None, run_id: str, result: dict, rows: list[dict]) -> None:
    """Keep the latest run per system in the snapshot the app shows."""
    from datetime import datetime, timezone

    data = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {"labels": "draft", "systems": {}}
    data["systems"][system] = {"run_id": run_id[:8], "model": model, "exported": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                               "metrics": result["metrics"], "confusion": result["confusion"], "drivers": DRIVERS,
                               "probes": [{k: r[k] for k in ("id", "question", "expect", "got", "seconds")} for r in rows]}
    SNAPSHOT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
