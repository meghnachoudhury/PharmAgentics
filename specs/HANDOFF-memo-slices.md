# Handoff: memo brief, slices 2 to 5

**Progress (2026-11-20, 04:10):** slices 1, 2 and 3 are done and committed (`dcf616d`, `68b6a51`). Latest gate runs to compare against: scripted `060132b35cc1`, agent `43c24bc0a892`. Parallel agent runs (`MLFLOW_GENAI_EVAL_MAX_WORKERS=4`) are verified safe. Next: slice 4, then slice 5. `.specify/feature.json` points at `specs/brief-006-follow-ups`. The headless-Chrome check scripts used so far live in the session scratchpad and may be gone; the approach is in `specs/brief-003-narrative-renderer/plan.md` (slice 2) and `specs/brief-006-follow-ups/tasks.md` (T008).

For a Claude session that continues this work without Michael present. Every decision below was made with him on 2026-11-19 and 2026-11-20; do not reopen them. If something is not covered here or in the specs, stop and leave a note rather than guess.

## Where the work lives

- Worktree `C:\Users\micha\test_agent_v1\PharmAgentics-memo`, branch `feature/brief-memo-follow-ups`. Enter it with EnterWorktree (path). Another session edits the main tree (`feature/eval-telemetry`): never touch it, never `git stash`, commit by path.
- `.specify/feature.json` points at `specs/brief-003-narrative-renderer` for slice 2; switch it to `specs/brief-006-follow-ups` for slices 3 and 4 and to `specs/core-008-uat-feedback` for slice 5.
- `local/pharmagentics.duckdb` in the worktree already has `reporting.v_rx_projection`; `.env` holds `ANTHROPIC_API_KEY`.
- MLflow store: `eval/mlflow/` in the worktree (a copy of the main store plus this branch's runs).

## Rules for an unattended session

- Allowed: `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`, tests, eval runs, `eval gate`, commits on this branch.
- Not allowed: merge, push, pull request, deploy, Drive edits, Keycloak changes, anything in the main tree.
- Gate every slice: a scripted run and an agent run (`--model anthropic:claude-haiku-5-5`) against the previous slice's final runs. A failed gate stops the night: fix if the cause is clear and inside the slice, rerun once, otherwise commit the work in progress on the branch with a note in that slice's `tasks.md` and stop.
- Agent runs may use `MLFLOW_GENAI_EVAL_MAX_WORKERS=4` only if a run with it logs one trace per case and every score; otherwise leave the default of 1.
- The agent's MCP server reloads `src/` for every case: never edit `src/` or the agent's prompts while an agent run is going.
- Every number is a claim token; every projected or estimated level says it is an assumption (brief-003 FR-022).

## Slices

| Slice | Spec | Scope | Decisions |
| :- | :- | :- | :- |
| 1 | brief-003 | Memo outline, projected national | Done 2026-11-20 (see `specs/brief-003-narrative-renderer/tasks.md`) |
| 2 | brief-003 FR-024 to FR-027 | Charts with captions and explanations, the data behind each section (query toggle, CSV), sections in the UI, leadership cut of sections | Inline SVG, no new library; baseline band = min to max of the baseline weeks; second panel = first supported driver, none supported means TRx only; CSV built in the browser; real-app check at the end (local app with `PHARMAGENTICS_AUTH=dev`, and the Bombadil spec in WSL if available) |
| 3 | brief-006 | Threads, the message bar, scripted follow-ups, save and share, 30-day purge | brief-006 Session 2026-11-20 |
| 4 | brief-006 | Haiku follow-ups, harness support for two turns, `sections_exist` check, six draft two-turn cases | brief-006 Session 2026-11-20 |
| 5 | core-008 FR-019 to FR-022 | `eval improve`, the agent reviewer step, the Feedback review tab (tester admin only), the approval queue, `eval promote`, lessons read by the agents | core-008 Session 2026-11-20 |

Keep `App.tsx` and `Telemetry.tsx` changes to a few lines: put new UI in new files, because the other session has uncommitted edits to both.

## When done

Write the run IDs and gate output into each slice's `tasks.md`, update `eval/README.md`, and update the memory file `brief-memo-redesign.md`. Leave a summary for Michael at the top of this file.
