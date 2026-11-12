# Implementation Plan: brief-002 Phase B — build 3 (the Briefing agent) and live runs on the owner's machine

**Branch**: `core-007-uat-deploy` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md) (FR-005, FR-007, FR-016, FR-025, FR-026); [core-007](../core-007-rbac-uat-deployment/spec.md) FR-028

## Summary

Build 3 puts the manager back on top of the Phase A code triage, keeps every number-bearing line in code, and lets UAT users run it live on Michael's PC.

1. **Triage (A1).** Code builds the Phase A plan. The manager (one structured LLM call) may reorder or drop proposed stories, sets each story's hypothesis order, and may mark the plan low-confidence; code rejects anything else. Departures and low confidence flag the plan. In UAT, P1 reviews every plan with the manager's calls shown (A10); in eval, the manager's plan runs and the record says whether it would have paused.
2. **Investigation.** One MCP session per run (one Registry, one data version). For each approved story, a bounded Magentic team (manager, Data Forensics, Driver Investigator; depth two) tests drivers with the MCP tools. A no-repeat ledger in the tool layer refuses a repeated test. Code closes any story the team left open (defined exit).
3. **Brief.** Code builds every section from the run's tool results (header, data health, restatements, KPIs, each story's head, the checks the agents actually ran, the confidence line, Metacora, dropped). The writer (LLM) adds only the direct answer and one sentence per story, using only that story's tokens. Verification fails typed digits, invented tokens, another story's tokens and banned terms; one revision; then the piece is dropped.
4. **Scope gate (C-024).** Questions the data cannot answer (rank channels or spend, ROI, patient-level, forecasts) get the scripted brief plus a scope statement; no loop.
5. **Live runs.** The app keeps a job queue. A worker on the owner's PC polls it outbound with a token, runs triage or brief jobs on Ollama, posts results; the app checks traceability before anyone sees them. The UI offers "Agent (runs on the owner's PC)" with host status, and a free-form question.

## Technical Context

**Language/Version**: Python 3.12; TypeScript 5.9

**Primary Dependencies**: Microsoft Agent Framework (Magentic orchestration, as in build 2), the PharmAgentics MCP server, Ollama `qwen3:4b-instruct-2507-q4_K_M` (12K context, one model on a 6 GB GPU), httpx (worker), FastAPI (app)

**Storage**: Jobs as JSON documents in the core-007 store (bucket on Cloud Run); the queue index in app memory (app capped at one instance so the index is authoritative; rebuilt from the bucket at start)

**Testing**: pytest for the pure parts (scope gate, triage validation, writer verification, assembly, queue, worker protocol) with a stub model; one Ollama-marked smoke test; `eval run --system briefing_agent` on the 24 Briefing cases and `eval gate` against the scripted baseline on the gated checks

**Target Platform**: Agent and worker on the owner's Windows PC; app on Cloud Run

**Performance Goals**: About 1 to 4 minutes per question on the local GPU; caps keep every run under 7 minutes

**Constraints**: No model on GCP (core-007 FR-016); Ollama never exposed; one job at a time on the GPU; no eval import from agents or src; free tiers (worker polls every 10 s only while it runs)

**Scale/Scope**: 24 Briefing golden cases; a handful of UAT users

## Constitution Check

| Article | How Phase B meets it |
| :- | :- |
| I. Every number from a tool | Code builds every number-bearing line; the writer may only place tokens; verification fails typed digits and foreign tokens; the app re-checks posted results |
| II. People decide | P1 reviews every plan in UAT and approves every brief before leaders see it |
| III. Isolation | The agent and worker import no eval code; the eval harness imports the agent |
| IV. Typed contracts | Manager triage output is JSON validated by pydantic against the code plan; jobs and results are typed; results carry data version and evidence |
| V. Abstain | Untested drivers keep a story at Medium or Low; a capped story closes "unresolved, investigate next" |
| VII. Loops end | Depth two, catalog-only drivers, no-repeat ledger, per-story round and wall caps, a run cap; code closes open stories |
| B-II | The stage flow names each agent and the tools it called |
| B-VII | `briefing_agent` is a new system: it must equal the scripted baseline on every gated check before it is offered in UAT; the scripted and low-code baselines stay runnable (the no-repeat ledger is off unless the agent turns it on) |

## Project Structure

```text
agents/brand-briefing/briefing_agent/   NEW build 3
├── __init__.py          answer() for eval; triage(); run_with_plan()
├── agent.yaml           model, caps, participants, prompts
├── prompts/             manager_triage.md, manager.md, data_forensics.md, driver_investigator.md, writer.md, revise.md
├── scope.py             code scope gate
├── plan.py              manager triage: prompt, parse, validate against the code plan, flag
├── investigate.py       per-story Magentic team over one MCP session; code closes open stories
├── write.py             evidence pack, writer, verification, revision, assembly, flow
└── worker.py            polls the app, runs jobs on Ollama, posts results
agents/brand-briefing/run_worker.py     entry point: uv run python agents/brand-briefing/run_worker.py
src/pharmagentics/mcp_server/server.py  admin section tools; opt-in no-repeat ledger
src/pharmagentics/api/jobs.py           NEW queue: submit, next, complete, status, host heartbeat
src/pharmagentics/api/app.py            /api/agent/* (analyst), /api/worker/* (worker token)
eval/harness/systems.py                 briefing_agent system
frontend/figma-make/src/                engine choice, host status, question box, job polling, manager calls on cards
deploy/                                 worker token secret; app max instances 1
tests/test_agent_build3.py, tests/test_jobs.py
```

## Complexity Tracking

| Addition | Why | Simpler alternative rejected |
| :- | :- | :- |
| Job queue and worker | Live agent runs with no model on GCP and no inbound path to the PC | Tunnel to Ollama (exposes the PC, holds requests for minutes); snapshots only (no live questions) |
| App capped at one instance | The queue index lives in memory | A bucket listing per poll costs Class A operations every 10 s |
