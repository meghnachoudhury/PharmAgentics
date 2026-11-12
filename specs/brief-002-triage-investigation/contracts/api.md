# HTTP contract additions: brief-002 Phase A

Adds to the core-007 API. All routes need a signed-in user; types are in [data-model.md](../data-model.md).

## POST /api/briefing/triage

Role: Briefing analyst (action `run`). Others: 403. Not signed in: 401.

Request: the core-007 `BriefingQuery` (`intent`, `brand_id`, `territory_id`, `week_start`, `question`).

Response 200 (`Cache-Control: no-store`): `TriagePlan`.

Errors: 400 week or territory outside the release; 503 no database.

UAT event: `triaged` with role, pseudonymous user, latency, `plan_id`, number of cards.

## POST /api/briefing/query (changed)

Request: `BriefingQuery` plus optional `triage: TriageDecision`.

- No `triage`: unchanged behavior (the default plan, no triage record of P1's calls).
- With `triage`: recompute the plan; `plan_id` mismatch → **409** "The triage plan changed; review it again."; a story ID not proposed for investigation → **400** naming the ID; else run stages 4 to 6 on the decision.

Response 200: the analyst view, plus `flow` (StageFlow) and `triage` (TriageRecord).

## GET /api/briefing/{brief_id}?view=

Analyst view: adds `flow` (with stage 7 set from the review state) and `triage`. Leadership view: unchanged; never carries `flow`, `triage`, claims or evidence.
