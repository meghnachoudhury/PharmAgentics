# Role-aware commercial questions

Requested by Meghna, 2026-11-13. Add a conversational workspace for every existing role without replacing Briefing, Forecast, triage, evidence, saved runs or review controls.

## Acceptance contract

- Each authorized lane has an **Ask PharmAgentics** entry, a transcript, question composer, backend-provided scope and saved-report choices. Follow-ups retain explicit scope and previous question intent within the current browser session; no conversation survives sign-out or crosses lane/role boundaries.
- Commercial analysts can ask read-only BXA TRx/NRx/NBRx, market share, prior-week comparisons, feed-health and forecast-versus-actual questions. Natural-language dates/territories override selectors explicitly in the returned scope. Unsupported questions, conflicting dates and unavailable cuts produce an explanation, never a made-up answer or an unrelated generic brief.
- Metrics use Registry and governed reporting views, code-filled claims, source SQL and pinned data versions. Missing/duplicate/restated cuts remain withheld. Multiweek national totals use territories reportable throughout the requested window, with coverage stated.
- Questions about explanations, next checks and review state use saved lane reports. New investigations remain in the existing workspaces and their review workflows.
- The Briefing Director can read only currently approved briefs from the current data version. The Forecast Brand Manager can read only submitted runs, using the existing visibility rule. Leadership chat is built from the existing server-shaped leadership response; it carries no claims, evidence, SQL or trace. The chat cannot submit, approve, reject, execute SQL or escalate roles.
- Authentication and lane/action permissions are checked on every endpoint. Extra request fields are refused. Arbitrary browser history, system prompts and proposed answers are never accepted as evidence.
- The interface identifies this as source-backed, deterministic Q&A. A conversational appearance does not imply unrestricted model reasoning. Nothing silently falls back to samples if the backend is unavailable.

## Verification

API tests cover exact metric reconciliation, distinct intents, missing/duplicate gates, natural-language and follow-up scope, unsupported questions, immutable review state, all four roles, cross-lane/unsigned requests, and leadership payload redaction. Browser checks cover every role, citations, follow-ups, errors, mobile layout and preservation of the existing workflows. Run TypeScript, the standalone Vite build and the full regression suite.
