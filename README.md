# PharmAgentics

A multi-agent AI platform that helps pharma commercial teams see what moved a brand and why. One agent tracks weekly brand performance, and the other explains forecast swings in plain language. Both run on a shared data layer and orchestration, and every number they state traces back to the data.

## Where it stands

| Piece | Status |
| :- | :- |
| Data foundation | Done. 14 supplied synthetic datasets load into a persistent DuckDB database. Missing and duplicate feed artifacts are preserved and reported, and weekly Rx KPIs are gated by feed health |
| Shared tools | Governed read-only queries over the data, evidence items and claim tokens, so every number is filled by code and traceable to its SQL |
| Eval harness | Done. 42 golden questions (24 Briefing, 18 Forecast), code checks, an optional local LLM judge, two controls, and runs, traces and spans in MLflow |
| Scripted baselines | One per agent, no model. Both state correct, traced numbers but only about a third of the numbers each answer expects, which is the gap the next versions close |
| Low-code and agent versions | Next. They plug into the harness and are scored on the same questions |
| Gemini integration | Future work |

## The two agents

- **Brand Briefing:** a weekly brand-performance briefing. Claims are tokens filled by code, so no digit comes from a language model.
- **Forecast Explanation:** plain-language explanations of forecast swings.

Both sit on the shared data layer and orchestration in `src/pharmagentics/`.

**Team:** how to use, host, run and deploy the web app is in [TEAM.md](TEAM.md).

## Hosted app and logins

**App:** https://pharmagentics-app-18389319270.us-central1.run.app (synthetic data only; the first sign-in after a quiet spell takes 15 to 30 seconds while the sign-in service wakes up).

| Login | Password | Role |
| :- | :- | :- |
| `uat-briefing-analyst` | `1kS0UoPCUFR9aqw4` | Commercial Analyst (P1), Weekly briefing |
| `uat-briefing-director` | `J41a1R8lgkZUmkv2` | Brand Director (P3), Weekly briefing |
| `uat-forecast-analyst` | `UHzTdiSH0hPIHmnC` | Commercial Analytics Analyst (CA), Forecast explanation |
| `uat-forecast-manager` | `eIaf0-YtGvg7nPca` | Brand Manager (BM), Forecast explanation |
| `uat-tester` | `BjpYK5HgqNCObxxL` | Test view: both lanes; "View as" in the account menu switches between Analyst (P1, CA) and Leadership (P3, BM) |

The same passwords work on the local stack (`deploy/make_env.py`, then `docker compose up --build`); they come from [`deploy/demo-credentials.env`](deploy/demo-credentials.env). They are shared on purpose: this is a class project on synthetic data. The service secrets in `deploy/.env.uat` are not, so keep that file out of git.

**Update, 2026-11-19:**

> Sign-in on the hosted app is fixed (a Keycloak redeploy that day had put its client secret out of sync with the app). There are now five logins: the four role logins Sienna shared, plus `uat-tester`, which switches between the Analyst and Leadership views of both lanes from the account menu. The `mentor-*` logins are gone. Passwords are in the table above and in `deploy/demo-credentials.env`. If you ran `env-pull` on 2026-11-19, run `uv run python deploy/gcp.py env-pull --project pharmagentics --account <you> --force` to get the right worker token. Before `env-push` or `gcp.py keycloak`, please check with Michael: those replace the live secrets for everyone.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
`uv sync` in the repository root. It installs Python 3.12 if needed and every
dependency pinned in `uv.lock`, the same on Windows, macOS and Linux. Python 3.11+
is the supported floor. Run commands through uv.

## Quick start

```powershell
uv run python src/pharmagentics/data/load_duckdb.py     # build the DuckDB database
uv run python src/pharmagentics/data/check_duckdb.py    # data checks
uv run pytest                                           # data, tools and eval tests
uv run python -m eval check                             # validate the 42 golden cases
uv run python -m eval run --system briefing_scripted --lane briefing
uv run python -m eval ui                                # MLflow dashboard, http://127.0.0.1:5000
```

See [DuckDB first-run instructions](docs/DUCKDB_FIRST_RUN.md) for installation, data checks and example queries, and [the eval harness](eval/README.md) for every command, check and result.

## Layout

| Path | Holds |
| :- | :- |
| `src/pharmagentics/` | Shared data layer and orchestration: data loader and checks, governed tools, tracing |
| `agents/brand-briefing/` | Briefing agent and its scripted baseline |
| `agents/forecast-explanation/` | Forecast agent and its scripted baseline |
| `eval/` | Golden set, scorers, controls and the MLflow store |
| `specs/` | Spec Kit specs for each component |
| `docs/planning/` | Markdown copies of the source documents |
| `data/agent_visible/` | The 14-table synthetic release |

## Ground rules

- The answer key and held-out cases live outside this repository. Agent code never reads `eval/`.
- Agents read data only through the governed views, never raw tables.
- No output line identifies an individual rep.
- "Competitive intelligence", never "surveillance". "New patients" only for NBRx.

`CLAUDE.md` holds the full instructions for coding agents.
