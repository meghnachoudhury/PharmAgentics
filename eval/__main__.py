"""python -m eval {import-stories, check, run, gate, candidates, export-telemetry, import-uat, ui}"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m eval", description="PharmAgentics golden-set evaluation.")
    sub = p.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import-stories", help="draft missing case files from docs/planning/user-stories.md")
    imp.add_argument("--force", action="store_true", help="overwrite existing case files (loses hand edits)")

    sub.add_parser("check", help="validate the golden set and recompute every fact from the data")

    run = sub.add_parser("run", help="score a system on the golden set and log it to MLflow")
    run.add_argument("--system", required=True, choices=["reference", "naive_llm", "briefing_scripted", "forecast_scripted",
                                                          "briefing_lowcode", "briefing_agent", "forecast_rules", "forecast_agent",
                                                          "forecast_investigator"])
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

    cand = sub.add_parser("candidates", help="draft golden-set candidates from UAT votes on answers (core-008)")
    cand.add_argument("--state-dir", type=Path, help="downloaded state folder (default: local/feedback-export, else local/state)")
    cand.add_argument("--force", action="store_true", help="overwrite existing drafts (loses hand edits)")

    imp2 = sub.add_parser("improve", help="propose lessons and cases from votes and saved threads (core-008 FR-019)")
    imp2.add_argument("--state-dir", type=Path, help="state folder to read and write (default: local/feedback-export, else local/state)")
    imp2.add_argument("--baseline", help="agent run to gate the candidate lessons against; without it no lesson is confident")
    imp2.add_argument("--model", help="drafting and reviewing model (default anthropic:claude-haiku-5-5)")
    prom = sub.add_parser("promote", help="write approved lessons and cases (core-008 FR-021); prints the git steps")
    prom.add_argument("--state-dir", type=Path, help="state folder holding review/proposals (default as for improve)")

    sub.add_parser("export-telemetry", help="write the golden-set scores the hosted app shows (src/pharmagentics/api/telemetry.json)")
    uat = sub.add_parser("import-uat", help="log the hosted app's live use to MLflow (experiment pharmagentics-uat)")
    uat.add_argument("--state-dir", type=Path, help="downloaded state folder (default: local/uat-export)")

    drv = sub.add_parser("drivers", help="Forecast driver recovery on the draft probes, with a confusion matrix (fcst-001)")
    drv.add_argument("--system", required=True, choices=["forecast_rules", "forecast_investigator"])
    drv.add_argument("--model", help="model for forecast_investigator, e.g. ollama:qwen3:4b-instruct-2507-q4_K_M")

    sco = sub.add_parser("scopes", help="Forecast question reading on draft paraphrases: rules or a model (fcst-002)")
    sco.add_argument("--reader", required=True, choices=["rules", "model"])
    sco.add_argument("--model", help="model for --reader model, e.g. ollama:qwen3:4b-instruct-2507-q4_K_M")

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

    if args.cmd == "improve":
        from .harness import improve
        made = improve.run(args.state_dir, baseline=args.baseline, model=args.model)
        for p in made:
            print(f"{p['id']} {p['kind']:<6} {'confident' if p['confident'] else 'flagged':<9} {p['source']}"
                  + (f"  ({'; '.join(p['reasons'])})" if p["reasons"] else ""))
        print(f"{len(made)} new proposal(s); review them on the Evaluation page (tester admin).")
        return 0

    if args.cmd == "promote":
        from .harness import promote
        out = promote.run(args.state_dir)
        print(f"lessons promoted: {len(out['lessons'])}; cases drafted: {len(out['cases'])}; skipped: {len(out['skipped'])}")
        for line in out.get("git", []):
            print("  " + line)
        return 0

    if args.cmd == "gate":
        from .harness.run import gate as run_gate
        return run_gate(args.candidate, args.baseline)

    if args.cmd == "candidates":
        from .harness import candidates
        written, kept, state_dir = candidates.run(args.state_dir, force=args.force)
        if state_dir is None:
            print("No votes found. Download them first: uv run python deploy/gcp.py feedback --project pharmagentics "
                  "--account <you>, or pass --state-dir.")
            return 1
        print(f"read votes from {state_dir}")
        print(f"wrote {len(written)} draft(s), kept {len(kept)} existing draft(s) in {candidates.CANDIDATES_DIR}")
        for path in written:
            print(f"  {path.relative_to(candidates.EVAL_DIR)}")
        print("A draft is not a case: review it, write its facts, give it an ID and move it into eval/golden/<lane>/.")
        return 0

    if args.cmd == "export-telemetry":
        from .harness import telemetry_export
        snap = telemetry_export.export()
        print(f"wrote {telemetry_export.OUT} ({len(snap['runs'])} runs, {len(snap['latest'])} system/lane pairs)")
        return 0

    if args.cmd == "import-uat":
        from .harness import uat_import
        run_id = uat_import.run(args.state_dir or uat_import.DEFAULT_DIR)
        if run_id is None:
            print("No downloaded state. Fetch it first: uv run python deploy/gcp.py uat --project pharmagentics "
                  "--account <you>, or pass --state-dir.")
            return 1
        print(f"logged run {run_id} to experiment {uat_import.EXPERIMENT}")
        return 0

    if args.cmd == "drivers":
        from .harness.drivers import run as drivers_run
        from pharmagentics.llm import model_spec

        drivers_run(args.system, model_spec(args.model) if args.system == "forecast_investigator" else None)
        return 0
    if args.cmd == "scopes":
        from .harness.scopes import run as scopes_run
        from pharmagentics.llm import model_spec

        scopes_run(args.reader, model_spec(args.model) if args.reader == "model" else None)
        return 0
    if args.cmd == "ui":
        from .harness.paths import MLFLOW_DIR, tracking_uri
        MLFLOW_DIR.mkdir(parents=True, exist_ok=True)
        print(f"MLflow dashboard: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
        return subprocess.call([sys.executable, "-m", "mlflow", "ui", "--backend-store-uri", tracking_uri(),
                                "--port", args.port])
    return 2


if __name__ == "__main__":
    sys.exit(main())
