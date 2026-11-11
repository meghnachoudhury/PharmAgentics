# PharmAgentics: backend feature audit and future enhancements

**Audit date:** 2026-11-06. **Repository:** `mwc2150/PharmAgentics` `main` at `ede7189af2` (checked before this patch).

## What is actually available

| Capability | Backend state | Frontend in this package |
|---|---|---|
| Synthetic data and persistent DuckDB | Implemented in `main` (14 CSV tables) | Accessed only through the API |
| Feed health and governed KPI views | Implemented | Shown only in backend narrative and evidence |
| Fixed Briefing pipeline | Implemented; `briefing_baseline.answer()` | **Enabled** via proposed FastAPI bridge |
| Evidence items and claim→evidence IDs | Implemented by Registry | **Enabled** in evidence drawer |
| Question-to-period/territory parsing | Implemented but limited rules | Structured selectors; no promise of natural-language parsing |
| Agentic Magentic-One Briefing | Implemented but evaluation still has regressions | **Not exposed**; scripted only |
| MCP tools | Implemented, internal to agent lane | No direct browser access |
| Evaluation harness/MLflow | Implemented | Not exposed in user-facing app |
| Forecast baseline | Implemented in `main`; separate workbench API on Alvin's branch | Not exposed through Briefing API |
| Browser HTTP Briefing service | **New files in this package; not yet merged into main** | Required for live frontend |

## Future enhancements — do NOT expose as active UI until backends exist and pass tests

1. **Free-form conversational analysis:** requires a production API for intent routing, conversational state, calibrated tool selection, unsupported-query handling, and appropriate result schemas. The scripted baseline currently produces a fixed weekly brief regardless of the semantic phrasing of the free-text question.
2. **Magentic-One-driven online Briefing:** existing low-code agent must meet the evaluation gate and be exposed as a bounded, authenticated HTTP execution service before UI allows engine switching.
3. **Forecast-Explanation:** Alvin's `alvin-forecast-explanation` branch has FastAPI workbench endpoints; after branch reconciliation, unified integration contract, and tests, expose a separate Forecast entrypoint. Do NOT send forecast requests to `/api/briefing/query`.
4. **Review Queue / analyst approval / manager sign-off / publication:** requires persistent server-side run IDs, authenticated personas/roles, workflow state storage, review and revision endpoints, audit trail, and permission checks. Current backend only returns draft status; it cannot approve.
5. **History and saved investigations:** requires persistence, user/workspace authorization, run retrieval/search endpoints, and version-aware reopening. No local fake history list.
6. **Rich charts, per-chart drilldowns, and A2UI:** requires structured, traceable time-series and comparison data in the API response, not numbers extracted from natural-language text or browser fixture tables.
7. **Dynamic brand portfolio:** backend supports index brand BXA only. Additional brands require their own validated metric definitions, supported pipeline semantics, API authorization, and evaluation cases before appearing as choices.
8. **Geography below territory / payer and specialty filters:** supported internal data grains do not imply safe HTTP contracts or user-facing review handling. Add dimension-specific endpoints and privacy/quality gates before UI.
9. **Interactive driver-attribution cards:** backend narrative includes driver checks, but its current public contract lacks structured per-driver verdict/evidence linkage. Add typed results, verified associations/causality levels, and tests first.
10. **Streaming progress and actual tool replay:** current API returns one completed JSON response; no reliable server event stream, so do not animate fake 'agent thinking' traces.
11. **Authentication, multi-user security, and deployment:** current FastAPI is local development-only; CORS is not authorization. Requires identity, secrets, rate limits, network controls, per-user audit, and HTTPS before public use.
12. **Clinical/patient-level analysis:** out of project scope; source data are entirely synthetic aggregate commercial records.

## Features intentionally removed from the Figma export

- Removed mock-backed `Dashboard.tsx`, `Overview.tsx`, `workspaces.tsx`, `charts.tsx`, `data.ts`, `flow.ts` and original `src/agent/` modules (`mockService`, `fixtures`, `Pages`, `Sidebar`, `review`, `session`, `DynamicChart`, etc.). These are **not silently preserved as navigable features**.
- No persona switcher, offline simulation switch, review approvals, sample forecast cases, fake tool timelines or demo tables.
- The original warm-ivory palette, branding and responsive chat-first visual layout are retained as a pared-down **Weekly Briefing** screen.

## Acceptance checks before considering integration complete

- Backend: synthetic DuckDB loads, `GET /api/briefing/context` lists real available weeks/territories, and `POST /api/briefing/query` returns non-empty evidence and claims for a valid sample.
- Frontend: no API URL → explicit error, no fake result; no HTTP server → explicit error, no fake result.
- Frontend: changed brand/territory/week → posted values match chosen options; options are returned by backend, not seeded by the UI.
- Frontend: evidence drawer shows actual `evidence_id`, `tool`, `query`, `data_version`.
- Frontend: displays only the scripted draft, not 'approved/published', and does not persist history.
- Existing repo CI and evaluation tests must remain green.
