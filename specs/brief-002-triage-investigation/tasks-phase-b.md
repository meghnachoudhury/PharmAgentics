# Tasks: brief-002 Phase B — build 3 and live runs

**Input**: [plan-phase-b.md](plan-phase-b.md), [spec.md](spec.md), core-007 FR-028. Tests included (eval-driven, B-VII).

## Phase 1: Shared tools

- [x] B001 In src/pharmagentics/mcp_server/server.py add admin tools `brief_sections` (header, data health, restatements, KPIs, withheld-focus line; JSON with token templates), `story_section(territory)` (head from `territory_change`, the checks the session ran in the order run, the closing confidence line), `competitor_section(lead)`, `dropped_line()`; add `RunSession(no_repeat=…)` (env `PHARMAGENTICS_MCP_NO_REPEAT=1`) so a repeated `check_*` on the same territory returns "Already tested" with the earlier result; default off, so builds 1 and 2 are unchanged
- [x] B002 [P] Tests in tests/test_agent_build3.py: sections equal the scripted pipeline's lines for 2026-07-13; no-repeat refuses a second `check_supply(PACIFIC)` only when on

## Phase 2: Build 3 agent (US1 to US5 of brief-002 on the agent)

- [x] B003 agents/brand-briefing/briefing_agent/scope.py: `out_of_scope(question) -> str | None` for channel or spend ranking, ROI, patient-level and forecast questions; tests with P4-Q6 ("Where should the next dollar go?") and in-scope questions
- [x] B004 agents/brand-briefing/briefing_agent/plan.py: `manager_plan(code_plan, question, chat)`: prompt from prompts/manager_triage.md with the cards; parse JSON `{order, drop: {id: why}, hypotheses: {id: [drivers]}, confidence: high|low, note}`; validate (only proposed IDs, drivers from `DRIVERS`); invalid output falls back to the code plan with the reason recorded; returns the plan with per-card `manager` calls, `flagged`, `manager_note`; tests with stub outputs (valid, reorder, drop, foreign ID, bad JSON)
- [x] B005 agents/brand-briefing/briefing_agent/investigate.py: one MCP session per run (no-repeat on); for each approved territory or plan story, a Magentic team (participants and caps from agent.yaml) with the story task (territory, hypothesis order, Data Forensics first); per-story round and wall caps; code calls `story_confidence` for a story left open; Metacora by code (`competitor_section`)
- [x] B006 agents/brand-briefing/briefing_agent/write.py: evidence pack per story; writer call (prompts/writer.md) returning JSON `{answer, stories: {id: sentence}}`; verification (typed digits, invented tokens, foreign tokens, banned terms "surveillance", "new patients" outside NBRx); one revision (prompts/revise.md); drop what still fails; assembly with code sections; the stage flow with agent names and tools; tests with stub writer outputs
- [x] B007 agents/brand-briefing/briefing_agent/__init__.py: `triage(question, model)`, `run_with_plan(question, decision, plan, model)`, `answer(question, model)` (eval: scope gate, code plan, manager plan, no person, investigation, write); envelope with trajectory (tools, LLM calls, caps, flagged, model, config version)
- [x] B008 agent.yaml and prompts/ (manager_triage, manager, data_forensics, driver_investigator, writer, revise)
- [x] B009 eval/harness/systems.py: register `briefing_agent`
- [x] B010 Run `eval run --system briefing_agent --lane briefing` (local Ollama; nothing else heavy at the same time); `eval gate <run> <scripted run>`; fix and rerun until the gated checks pass; record run IDs here

## Phase 3: Live runs (core-007 FR-028)

- [x] B011 src/pharmagentics/api/jobs.py: in-memory queue mirrored to the store (`jobs/<id>.json`); `submit`, `next` (one running job at a time), `complete`, `get`, host heartbeat on each poll, stale running job (over 10 min) marked failed; rebuilt from the store at start
- [x] B012 src/pharmagentics/api/app.py: `POST /api/agent/jobs` (analyst `run`; kinds `triage` and `brief`, the brief job names its triage job and carries P1's decision), `GET /api/agent/jobs/{id}`, `GET /api/agent/status`; `POST /api/worker/next` and `POST /api/worker/jobs/{id}` with `Authorization: Bearer <PHARMAGENTICS_WORKER_TOKEN>` (constant-time compare); a posted brief passes the traceability check on the app's data version (else the job fails) and is saved with engine `agent`; schemas widen `engine` to `scripted | agent`
- [x] B013 [P] tests/test_jobs.py: worker endpoints refuse a missing or wrong token; analysts submit, directors cannot; one job at a time; a result with a number that is no claim fails the job; status online after a poll and offline after 60 s
- [x] B014 agents/brand-briefing/briefing_agent/worker.py and agents/brand-briefing/run_worker.py: poll every 10 s, run the job with the local model, post the result or the error; token and app URL from deploy/.env.uat or flags
- [x] B015 deploy: `PHARMAGENTICS_WORKER_TOKEN` in deploy/make_env.py, a fourth secret in deploy/gcp.py setup and app deploy, app `--max-instances=1`; compose passes the token
- [x] B016 UI (frontend/figma-make/src): engine choice (Scripted / Agent on the owner's PC with online or offline), a question box for the agent, job polling with queued and running states, the manager's calls and the flag on triage cards, engine and model labels on agent briefs

## Phase 4: Ship

- [x] B017 Full test suite; docker compose with a local worker end to end (sign in, agent triage, approve, brief)
- [x] B018 Deploy to Cloud Run; run the worker against the cloud app; end-to-end check; commit

## Notes

- Eval: `e994d094d9b3` (first) and `08364597fd95` (after the plan fixes): every gated check equals the scripted baseline `ba76420932c3` (`eval gate` passes); 0 run errors, 0 caps, about 50 s a case; golden-number recall 0.375 against 0.388 (report only). Investigated cases 10 to 12 of 24; flagged plans 13 to 8.
- Local end to end (B017): worker on Ollama, real Keycloak sign-in; triage job 15 s, brief job 81 s; leadership view clean.
- Known limits of the 4B model: the manager drops the Metacora story too readily (flagged for P1); the writer can misdescribe what a claim compares ("against the week before" for a four-week baseline). Code checks catch wrong numbers, not wrong wording; the judge (report only) and P1 review cover that.
- Cloud (B018, 2026-11-11): worker on the owner's PC against Cloud Run; triage job 18 s, brief job 89 s; traceability check passed; leadership view clean; test brief and jobs deleted from the bucket.
