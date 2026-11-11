# PharmAgentics

Multi-agent first-pass forensic analyst for pharma brand performance. Course capstone (IEOR4573E, Columbia, Fall 2026; mentor Dr. Fikreab S. Admasu). One shared platform (a shared data layer and orchestration layer), a seven-stage spine, and two use cases: the Weekly Brand-Performance Briefing Agent (Michael, Meghna) and the Forecast-Explanation Agent (Alvin, Sienna). The Proposal dropped two earlier use cases (payer-access impact; HCP segmentation and next-best action); do not bring them back.

Since 2026-10-29 development is eval-driven: every version of each agent answers the same 42 golden questions in `eval/` and is scored in MLflow. Specs are written with Spec Kit.

This file is the single set of instructions for coding agents; `AGENTS.md` only points here.

## Read first

- `SoT/README.md`: where the source documents come from and how a new drop updates Spec Kit
- `docs/planning/README.md`: Markdown copies of the source docs and their precedence (Proposal, then each lane's personas and evaluation pack, then the System Architecture, then each lane's architecture doc)
- `.specify/memory/constitution.md` (shared, v2.0.0) and `.specify/memory/constitution-briefing.md` (Briefing lane, v1.0.0)
- `specs/README.md`: spec index, shared decisions, open items, dev anchor cases
- `eval/README.md`: golden set, scorers, controls, and how to run and read results
- `data/agent_visible/README.md`, `data_dictionary.json`, `docs/DUCKDB_FIRST_RUN.md`: the data world

## Layout

```text
src/pharmagentics/             shared data layer and orchestration: data/ (loader, checks), tools/ (governed read-only queries, evidence, claim tokens, the driver checks, question parser, stage steps), mcp_server/ (the tools over MCP; Proposed as the shared interface, S9), llm.py (agent model clients), tracing.py
agents/brand-briefing/         Briefing lane; briefing_baseline/ is its scripted baseline, briefing_lowcode/ its low-code build (Magentic-One over the MCP server)
agents/forecast-explanation/   Forecast lane; forecast_baseline/ is the scripted baseline BL-0 (draft for Alvin and Sienna); the rest of Alvin's code is on the alvin-forecast-explanation branch until it merges
eval/                          golden set (42 cases), scorers, controls, MLflow store (eval/mlflow/, git-ignored)
SoT/                           dated Drive exports of the source docs; drops git-ignored, README and check.py committed
docs/planning/                 Markdown copies of the source docs (what Spec Kit reads)
specs/                         core-### shared, brief-### Briefing, fcst-### Forecast (reserved)
data/agent_visible/            the 14-table synthetic release; local/pharmagentics.duckdb is built from it
tests/                         data-foundation tests
```

## Hard rules

- **Ground truth stays outside this repository.** The generator, answer key, pre-artifact true data, counterfactual components and held-out parameters live in a private store found through `PHARMAGENTICS_EVAL_STORE`. Never commit, read, open, grep, index or copy them. Only `eval/harness/store.py` may read that variable, and only for evaluation work the user asks for.
- **Agent code never reads `eval/`.** Nothing in `src/` or `agents/` imports the eval package or opens the golden cases; they are an answer key for development. `eval/tests/test_isolation.py` enforces this.
- **A SoT drop never holds ground truth.** Run `uv run python SoT/check.py` on every new drop; it refuses files that look like an answer key or held-out parameters.
- Agent tools read data only through the governed views over `data/agent_visible/` (DuckDB). Never read `raw` tables for metrics.
- No digit in any generated brief or report comes from a language model. Briefing uses claim tokens filled by code.
- Say "competitive intelligence", never "statistical surveillance" or "surveillance". "New patients" only for NBRx.
- No output line identifies an individual rep.
- Mark unknowns `[NEEDS CLARIFICATION: … (open-item ID)]`. Do not guess.
- Do not edit the Forecast lane's personas, evaluation (Sienna's Personas & Eval Design: FE-01 to FE-31, TC-01 to TC-12), constitution or specs; cite them by ID. The Forecast golden cases and any FE scorers are drafts until Alvin and Sienna confirm them.
- LLM judges are report-only until their agreement with human labels clears the bar (Evaluation Pack open item 2). Never gate a merge on a judge score before that.
- Do not push to GitHub or open pull requests unless the user asks.

## Workflow

**Eval loop.** Change a system, then `uv run python -m eval run --system <name>`, read the result in the MLflow dashboard (`uv run python -m eval ui`), and run `uv run python -m eval gate <candidate-run-id> <baseline-run-id>` before merging. No change merges if a gated check regresses (Briefing B-VII). A new system (the low-code version, then the agents) plugs in through `eval/harness/systems.py` and returns the answer contract in `eval/harness/envelope.py`: answer text, claims, evidence items. Reuse `src/pharmagentics/tools/` so every number stays traceable.

**Spec Kit.** `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement` → `/speckit-converge`, one spec per component. Spec Kit finds the active spec from `.specify/feature.json` (now core-007), not the branch name:

```powershell
'{"feature_directory":"specs/core-007-rbac-uat-deployment"}' | Out-File -Encoding ascii .specify/feature.json
```

Only the five `brief-###` specs (`brief-001` to `brief-005`, Briefing lane only) lost their `plan.md` and `tasks.md` on 2026-10-29; they are re-planned against the golden set. The `core-###` specs (both lanes) keep their plans. The Forecast lane has no specs in this repo yet (`fcst-###` is reserved for Alvin and Sienna).

**Source documents.** The masters are in Google Drive. A new export goes into `SoT/<YYYY-MM-DD>/`; run `SoT/check.py`, refresh the changed copies in `docs/planning/`, update the specs and golden cases that cite them, and log the drop in `SoT/README.md`. When reality disagrees with a spec, update the spec first, then the code.

## Build and run

Dependencies are managed with uv. `pyproject.toml` declares them, `uv.lock` pins one resolution for Windows, macOS and Linux, and `.python-version` pins Python 3.12 (the shared floor stays 3.11). `uv sync` installs the base plus the `dev`, `agent` and `eval` groups. Change dependencies only with `uv add` or `uv remove` (for example `uv add --group eval <package>`) and commit `uv.lock` with the change. `requirements.txt` is a generated pip fallback for the data foundation: `uv export --no-default-groups --no-hashes --no-emit-project -o requirements.txt`.

- Data: `uv run python src/pharmagentics/data/load_duckdb.py`, then `uv run python src/pharmagentics/data/check_duckdb.py`
- Tests: `uv run pytest` (data-foundation tests, `tests/test_tools.py` and `eval/tests/`)
- Golden set: `uv run python -m eval check` validates the 42 cases and recomputes every fact from the data
- Baselines: `uv run python -m eval run --system briefing_scripted --lane briefing` and `--system forecast_scripted --lane forecast`. They use no model; every number is a claim token filled from a stored SQL query
- Low-code agent: `uv run python -m eval run --system briefing_lowcode --lane briefing`. Local `qwen3:4b-instruct-2507-q4_K_M` on Ollama by default (needs tool calling: the gemma3 models have none); `--model gemini:` uses `GEMINI_API_KEY` and `GEMINI_MODEL` from the git-ignored `.env`. About a minute or more per case locally. The MCP server alone: `uv run python -m pharmagentics.mcp_server`
- Controls: `uv run python -m eval run --system reference` (golden answers; must score 1.0 on every code check) and `--system naive_llm` (local model with no data; must fail the numeric checks)
- Judge: add `--judge` for RAGAS judges on local Ollama `gemma3:4b` (no API credits; needs Ollama running). Later, `--judge gemini:/<model>` switches provider. Expect minutes per case on a laptop GPU, so judge on demand, not on every run
- Dashboard: `uv run python -m eval ui`, then http://127.0.0.1:5000
- Briefing web app (core-007): `uv run python deploy/make_env.py` once, then `docker compose up --build` (Keycloak on :8081, app on :8080; sign in as `uat-analyst` or `uat-director`). One image holds Meghna's UI (`frontend/figma-make`, built with `vite.config.standalone.ts`) and the API (`src/pharmagentics/api`) on one origin, scripted engine only; `.dockerignore` is an allow-list, so `eval/`, `SoT/` and `.env` never enter it. Roles live in `src/pharmagentics/api/roles.json` and the Keycloak realm in `deploy/keycloak/`; the server strips evidence from leadership responses. Without Keycloak: `PHARMAGENTICS_AUTH=dev` gives stand-in identities. Google Cloud: `deploy/README.md` (`deploy/gcp.py`)

MLflow telemetry is turned off in `eval/__init__.py`: it sends usage data to an external service and deadlocks parallel scorer threads in MLflow 3.17.
