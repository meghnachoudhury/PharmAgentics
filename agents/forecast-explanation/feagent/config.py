from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # agents/forecast-explanation
REPO_ROOT = ROOT.parent.parent
# The LUMINA engineering fixture lives in a throwaway file under the git-ignored local/ folder.
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", str(REPO_ROOT / "local" / "forecast_lumina.duckdb"))
PHARMAGENTICS_DATA_DIR = os.environ.get("PHARMAGENTICS_DATA_DIR", "")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
OLLAMA_TIMEOUT_SEC = float(os.environ.get("OLLAMA_TIMEOUT_SEC", "60"))

MAX_INVESTIGATOR_STEPS = int(os.environ.get("MAX_INVESTIGATOR_STEPS", "12"))
BRAND = "LUMINA"
METRIC = "TRx"
