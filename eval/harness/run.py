"""Run a system on the golden set and log one MLflow parent run with a child run per rerun."""
from __future__ import annotations

import os
import statistics
from pathlib import Path

import mlflow

from .cases import golden_fingerprint, load_cases
from .paths import EXPERIMENT, MLFLOW_DIR, tracking_uri
from .scorers import DETERMINISTIC, EVIDENCE, TRAJECTORY, judge_scorers
from .systems import SYSTEMS
from .versions import code_version, data_fingerprint


def configure(uri: str | None = None, experiment: str = EXPERIMENT, artifacts: Path | None = None) -> None:
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    mlflow.set_tracking_uri(uri or tracking_uri())
    if mlflow.get_experiment_by_name(experiment) is None:
        artifacts = artifacts or MLFLOW_DIR / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        mlflow.create_experiment(experiment, artifact_location=artifacts.as_uri())
    mlflow.set_experiment(experiment)


def run_suite(system: str, lane: str = "all", reruns: int = 1, judge: str | None = None,
              stories: list[str] | None = None, uri: str | None = None, experiment: str = EXPERIMENT,
              artifacts: Path | None = None, model: str | None = None) -> str:
    cases = load_cases(lane, stories)
    if not cases:
        raise SystemExit("No golden cases match; run `python -m eval import-stories` first.")
    sut = SYSTEMS[system](cases, model=model) if model else SYSTEMS[system](cases)
    scorers = (DETERMINISTIC + (EVIDENCE if sut.returns_evidence else [])
               + (TRAJECTORY if getattr(sut, "returns_trajectory", False) else []) + (judge_scorers(judge) if judge else []))
    os.environ["PHARMAGENTICS_TRACING"] = "1"  # stage and tool spans inside the system under test
    # One prediction at a time: parallel trace writes to the SQLite store lose traces to lock
    # contention, and a local model serves one request at a time anyway.
    os.environ.setdefault("MLFLOW_GENAI_EVAL_MAX_WORKERS", "1")
    if sut.uses_llm or judge:
        os.environ.setdefault("MLFLOW_GENAI_EVAL_LLM_TIMEOUT", "600")
    os.environ.setdefault("MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION", "True")

    configure(uri, experiment, artifacts)
    rows = [{"inputs": {"question": c.question}, "expectations": c.expectations()} for c in cases]

    # Traced here because skipping MLflow's first-row validation also skips its auto-tracing wrapper.
    errors: list[str] = []

    @mlflow.trace(name=f"{system}.predict", span_type="AGENT")
    def predict_fn(question: str) -> dict:
        try:
            return sut.predict(question)
        except Exception as exc:  # MLflow records the failure per row; count it so it is never read as a score
            errors.append(f"{question[:70]}: {type(exc).__name__}: {exc}")
            raise

    model = getattr(sut, "model", None)
    params = {
        "system": f"{system}:{model}" if model else system,
        "lane": lane, "cases": len(cases), "reruns": reruns, "judge": judge or "off",
        "golden_version": golden_fingerprint(None if lane == "all" else lane),
        "data_version": data_fingerprint(), "code_version": code_version(),
        **getattr(sut, "params", {}),  # e.g. an agent's configuration version
    }
    per_rerun: list[dict] = []
    with mlflow.start_run(run_name=f"{system} · {lane}") as parent:
        mlflow.log_params(params)
        mlflow.set_tags({"suite": "golden", "system": system, "lane": lane})
        for i in range(1, reruns + 1):
            with mlflow.start_run(run_name=f"{system} · {lane} · rerun {i}", nested=True):
                mlflow.log_params({**params, "rerun": i})
                errors.clear()
                result = mlflow.genai.evaluate(data=rows, predict_fn=predict_fn, scorers=scorers)
                metrics = {k: float(v) for k, v in result.metrics.items() if isinstance(v, (int, float))}
                metrics["run_errors/mean"] = float(len(errors))  # failure tag "run error" (Evaluation Pack section 8)
                mlflow.log_metric("run_errors/mean", float(len(errors)))
                if errors:
                    mlflow.log_text("\n".join(errors), "run_errors.txt")
                    print(f"  RUN ERRORS in rerun {i}: {len(errors)} of {len(cases)} cases crashed, e.g. {errors[0]}")
                per_rerun.append(metrics)
        keys = sorted({k for m in per_rerun for k in m})
        for key in keys:
            values = [m[key] for m in per_rerun if key in m]
            mlflow.log_metric(key, statistics.fmean(values))
            if len(values) > 1:
                mlflow.log_metric(key.replace("/mean", "") + "/rerun_std", statistics.pstdev(values))
    print(f"\nRun {parent.info.run_id} ({system}, {lane}, {len(cases)} cases, {reruns} rerun(s))")
    for key in keys:
        values = [m[key] for m in per_rerun if key in m]
        print(f"  {key:<40} {statistics.fmean(values):.3f}")
    return parent.info.run_id


def gate(candidate: str, baseline: str, uri: str | None = None) -> int:
    """Exit 1 when any gated code check scores lower than on the baseline run (Briefing B-VII)."""
    from .scorers import GATED

    configure(uri)
    client = mlflow.MlflowClient()
    cand, base = client.get_run(candidate).data.metrics, client.get_run(baseline).data.metrics
    failed = cand.get("run_errors/mean", 0) > base.get("run_errors/mean", 0)
    if failed:
        print(f"  run_errors/mean                  baseline {base.get('run_errors/mean', 0):.0f}  candidate {cand['run_errors/mean']:.0f}  REGRESSION")
    for name in GATED:
        key = f"{name}/mean"
        if key not in base or key not in cand:
            print(f"  {key:<32} missing on one run")
            continue
        drop = cand[key] < base[key] - 1e-9
        failed |= drop
        print(f"  {key:<32} baseline {base[key]:.3f}  candidate {cand[key]:.3f}  {'REGRESSION' if drop else 'ok'}")
    return 1 if failed else 0
