# Data model: brief-002 Phase A

Typed objects that cross the pipeline-API-UI boundary (shared Principle IV). Field names are the wire names.

## StoryCard

One candidate story in a triage plan.

| Field | Type | Rule |
| :- | :- | :- |
| `id` | string | `territory:<TERRITORY_ID>`, `plan:<plan_id>` or `competitor:BXE`; stable for the same release and question |
| `kind` | `territory` \| `plan` \| `competitor` | |
| `title` | string | Territory name, plan name, or "Competitor Metacora (continuing)" |
| `rank` | int | 1-based, by impact; Metacora after territory and plan stories |
| `proposed` | `investigate` \| `over_cap` | Over-cap cards cannot be chosen (B-V) |
| `what_moved` | string | Rendered from claims; no digit outside a claim value |
| `decision` | string | Why code flagged it, and the proposed action |
| `population` | string | Cuts that pass the gate, by territory name; withheld named |
| `granularity` | string | Territory, or the plan |
| `time` | string | Requested weeks and baseline weeks, as dates |

## TriagePlan

Returned by the triage step; not stored.

| Field | Type | Rule |
| :- | :- | :- |
| `plan_id` | string | `t-` + 12 hex; hash of question, data version and proposed IDs |
| `question`, `week_start`, `territory_id`, `data_version` | | Same as the brief |
| `state` | `TRIAGE_REVIEW` \| `ROUTINE` \| `CALENDAR` | ROUTINE when no candidate; CALENDAR when the period is a calendar week (no stories) |
| `stories` | StoryCard[] | Ordered by rank |
| `dropped` | `{territory, reason, layer: "code"}`[] | Quiet territories ("within their normal range") and withheld ones (feed-gate reasons) |
| `claims`, `evidence` | as in a brief | Every claim resolves to an evidence item on `data_version` |
| `flow` | StageFlow | Stages 1 to 3 done; stage 4 at TRIAGE_REVIEW |

## TriageDecision

Sent by P1 with the run request.

| Field | Type | Rule |
| :- | :- | :- |
| `plan_id` | string | Must equal the recomputed plan's ID, else 409 |
| `stories` | string[] | Ordered subset of the plan's `investigate` card IDs; anything else is 400; may be empty |

## TriageRecord

Stored with the brief; analyst view only.

| Field | Type | Rule |
| :- | :- | :- |
| `plan_id` | string | |
| `calls` | `{story, outcome, layer}`[] | `outcome`: proposed, investigated, dropped, moved, over_cap, quiet, withheld; `layer`: `code` or `human` |
| `default` | bool | True when P1 approved the plan unchanged |

## StageFlow

List of seven `Stage` objects; analyst view only.

| Field | Type | Rule |
| :- | :- | :- |
| `stage` | 1..7 | |
| `name` | string | Load and pin; Validation gate; Competitive intelligence; Triage and investigation; Narrative; Verification; Review and publish |
| `actors` | `{kind: code \| agent \| llm \| human, name}`[] | Scripted stage 4: `code: triage rules`, `human: Commercial Analyst (plan review)`, `code: fixed order of checks (manager off)` |
| `states` | string[] | Briefing §6 run-state names, in order reached |
| `note` | string | One line; no figure that is not code-computed |

Stage 7 states are set by the API from the review: `IN_REVIEW` (pending), `PUBLISHED` (approved), `RETURNED` (rejected).

## Brief record (core-007 store), additions

`triage` (TriageRecord) and `flow` (StageFlow) inside `result`; the leadership view's allow-list does not include them.
