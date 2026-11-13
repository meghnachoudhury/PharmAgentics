# Ask PharmAgentics

The chat workspace is additive. The existing Weekly Briefing, triage, evidence drawer, approvals, Forecast workbench, leadership preview and Brand Manager review remain available.

## Where to find it

In either authorized lane, choose **Ask PharmAgentics** in the sidebar. All four roles have the interface. An account with roles in both lanes has a separate conversation in each lane. Conversations stay in browser memory while navigating workspaces and clear on reload/sign-out; they are not persistent chat history or learning memory.

## Ask about the data

Analysts can select **Live governed metrics**, choose a territory/start week/window, and type questions such as:

- `How many BXA TRx prescriptions in Pacific on June 8, 2026?`
- `What is the market share?`
- `How did NRx change versus the previous period?`
- `Is the feed reportable in New England on 2026-05-04?`
- `What is the forecast variance for National on August 24, 2026?`
- `And the previous week?` (retains the preceding metric/intent and selected scope).

The response states its resolved scope. Natural-language territory names and ISO or full written dates can override selectors. Written dates need a year. Relative previous/next weeks refer to the selected reporting week, not today's date. Comparative windows use the preceding equal-length period. Invalid dates, unsupported geographies and ambiguous multi-date requests are refused instead of being guessed.

Live figures are computed without a language model. Read-only Registry queries provide claims, SQL source records and a pinned data version. Click an underlined claim or source button to inspect it. Missing, duplicate, incomplete and restated cuts stay withheld. National windows use territories passing throughout the requested/comparison periods, with coverage disclosed. An unavailable cut is never presented as zero demand.

## Ask about a report

Choose a saved source, then ask for its summary, drivers, next checks, review status, or (Forecast) residual/verification. These answers use the stored result, not fabricated new investigations. New investigations and approval/submission/rejection still use the existing workspaces.

- **Briefing analyst:** current-version saved briefs and live governed metrics.
- **Brand Director:** currently analyst-approved Briefing summaries only; no SQL, evidence or trace payloads.
- **Forecast analyst:** saved Forecast reports and live governed metrics.
- **Brand Manager:** submitted Forecast reports, using the existing visibility rule; executive-summary fields only, never analyst evidence or traces.

Without an accessible report, leaders can ask metric definitions but receive a clear explanation when a requested analysis requires an analyst's reviewed/submitted report. Report scope cannot be silently changed. A saved Forecast report contains TRx, not NRx/NBRx. Identical report requests retain their existing review state.

## Boundaries and errors

This is source-backed conversational Q&A with explicit intent routing. It is not unrestricted LLM dialogue. Clinical questions, other brands, arbitrary SQL and commands to change/release data are unsupported. Unsupported requests receive an explanation; a failed connection displays an error without a sample answer. The server never trusts browser chat history or accepts an answer supplied by the client.

`GET /api/chat/context?lane=briefing|forecast` returns role-filtered source/scope choices. `POST /api/chat/query` accepts lane, question, BXA scope, an optional accessible record ID, and the previous intent/metric for scoped follow-ups. Authentication, lane permissions and report visibility are checked on every request. Responses are `no-store`. UAT events record pseudonymous role/intent/status metadata, not question text.

## Why the old chat was missing

The historical Figma integration (`61a1ca6`) removed mock-backed prototype modules and exposed the then-supported fixed weekly-brief endpoint. Later UI work kept that form-driven layout. This change adds a real question API and conversation interface alongside the current capabilities rather than restoring mock responses.

See [core-008](../specs/core-008-role-aware-chat/spec.md) and `tests/test_chat_api.py` for the acceptance contract.
