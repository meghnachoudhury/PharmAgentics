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
