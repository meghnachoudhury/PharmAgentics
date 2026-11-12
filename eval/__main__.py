"""python -m eval {import-stories, check, run, gate, ui}"""
from __future__ import annotations

import argparse
import subprocess
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval", description="PharmAgentics golden-set evaluation.")
    sub = p.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import-stories", help="draft missing case files from docs/planning/user-stories.md")
    imp.add_argument("--force", action="store_true", help="overwrite existing case files (loses hand edits)")

    sub.add_parser("check", help="validate the golden set and recompute every fact from the data")

    run = sub.add_parser("run", help="score a system on the golden set and log it to MLflow")
    run.add_argument("--system", required=True, choices=["reference", "naive_llm", "briefing_scripted", "forecast_scripted",
                                                          "briefing_lowcode", "briefing_agent"])
    run.add_argument("--lane", default="all", choices=["all", "briefing", "forecast"])
    run.add_argument("--reruns", type=int, default=1)
    run.add_argument("--stories", help="comma-separated story IDs, e.g. P1-Q2,CA-Q1")
    run.add_argument("--judge", nargs="?", const="default", default=None,
                     help="add LLM judges; optional model URI (default ollama:/gemma3:4b)")
    run.add_argument("--model", help="model for agent systems: ollama:<model> or gemini:<model> "
                                     "(default PHARMAGENTICS_AGENT_MODEL, else the local default)")

    gate = sub.add_parser("gate", help="fail if a candidate run regresses on gated checks")
    gate.add_argument("candidate")
    gate.add_argument("baseline")

    ui = sub.add_parser("ui", help="open the MLflow dashboard on eval/mlflow")
    ui.add_argument("--port", default="5000")

    args = p.parse_args(argv)

    if args.cmd == "import-stories":
        from .harness import importer
        written = importer.run(force=args.force)
        print(f"wrote {len(written)} case file(s): {', '.join(written) or 'none (all exist)'}")
        return 0

    if args.cmd == "check":
        from .harness.cases import load_cases
        from .harness.integrity import check_facts, id_problems
        cases = load_cases()
        problems = id_problems(cases)
        results = check_facts(cases)
        bad = [r for r in results if not r.ok]
        lanes = {lane: sum(c.lane == lane for c in cases) for lane in ("briefing", "forecast")}
        print(f"cases: {lanes['briefing']} briefing, {lanes['forecast']} forecast; "
              f"draft {sum(c.status == 'draft' for c in cases)}, frozen {sum(c.status == 'frozen' for c in cases)}")
        print(f"facts: {len(results) - len(bad)} of {len(results)} recompute; "
              f"{sum(not c.facts for c in cases)} cases have no facts yet")
        for r in bad:
            print(f"  MISMATCH {r.case} {r.fact}: golden {r.expected!r}, data {r.actual!r}")
        for msg in problems:
            print(f"  {msg}")
        return 1 if bad or problems else 0

    if args.cmd == "run":
        from .harness.paths import DEFAULT_JUDGE
        from .harness.run import run_suite
        judge = DEFAULT_JUDGE if args.judge == "default" else args.judge
        stories = [s.strip() for s in args.stories.split(",")] if args.stories else None
        run_suite(args.system, args.lane, args.reruns, judge, stories, model=args.model)
        return 0

    if args.cmd == "gate":
        from .harness.run import gate as run_gate
        return run_gate(args.candidate, args.baseline)

    if args.cmd == "ui":
        from .harness.paths import MLFLOW_DIR, tracking_uri
        MLFLOW_DIR.mkdir(parents=True, exist_ok=True)
        print(f"MLflow dashboard: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
        return subprocess.call([sys.executable, "-m", "mlflow", "ui", "--backend-store-uri", tracking_uri(),
                                "--port", args.port])
    return 2


if __name__ == "__main__":
    sys.exit(main())
