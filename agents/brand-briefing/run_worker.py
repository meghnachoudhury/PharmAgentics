"""Start the local agent worker (core-007 FR-028): `uv run python agents/brand-briefing/run_worker.py --app <url>`.

Needs Ollama running with the agent model, the release loaded (local/pharmagentics.duckdb), and
PHARMAGENTICS_WORKER_TOKEN (deploy/.env.uat, written by deploy/make_env.py)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "src")]

from briefing_agent.worker import main  # noqa: E402

if __name__ == "__main__":
    main()
