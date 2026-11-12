# Five-question triage (data plan)

Copy of the course slide "Five-question triage: run any analysis through this before licensing anything", added to SoT drop 2026-11-11 (`Five-question triage (data plan).png`) by Michael. Course reference for the term-project data plan; it sits outside the precedence order in [README.md](README.md) and changes no requirement on its own.

## The slide

| # | Question | Asks |
| :-: | :- | :- |
| 1 | Decision | What decision does this inform: brand strategy, targeting, access, medical, forecasting? Who acts on it? |
| 2 | Population | Sizing a universe (needs projected, open data) or measuring within a defined cohort (needs observed, closed data)? |
| 3 | Granularity | Patient-level (claims, EHR), HCP-level (projected Rx, CRM), HCO-level (DDD) or geo-level (census)? |
| 4 | Time | Real-time decisioning (CRM, digital), weekly brand tracking (panels) or quarterly outcomes (closed claims)? |
| 5 | Cost and rights | License cost, refresh, what you may link, what you may not re-identify, and whether the vendor allows model training |

## Two different triages

This slide triages **data and analyses before anyone licenses data**. The Briefing agent's stage-4 triage (Briefing Architecture §5.4, brief-002 User Story 1) triages **candidate changes in a week**: which to investigate, grouped how, in what order, with P1 reviewing flagged plans in `TRIAGE_REVIEW`. They answer different questions; neither replaces the other.

The slide's first four questions still help stage 4: they are the questions a triage plan should answer for each story, so that P1 can approve or edit it quickly.

| Slide question | Asked of one story in a stage-4 triage plan | Where the repo already answers or misses it |
| :- | :- | :- |
| Decision | Who acts on this story? | Each story closes with "Next: involve …" (scripted baseline; brief-002) |
| Population | Is the change measured on the cuts that pass the feed gate (like for like), or on all cuts? | Validation gate and "7 of 8 territories" labels (core-003) |
| Granularity | At what grain is the change real: territory, plan, specialty? | Missed in low-code trace C-022: it quoted the territory (815 vs 730 TRx) where the golden answer needs the Part D plan (183 → 218) |
| Time | Which weeks and which baseline window? | Window parser (`tools/window.py`); restatement window (S4) |

## The data plan, for the Briefing lane

| Question | Briefing lane answer | Source |
| :- | :- | :- |
| Decision | Weekly brand performance: what changed, is it real, why, who to involve. P1 prepares; P3 acts (core-007 roles) | Briefing personas; core-007 |
| Population | [NEEDS CLARIFICATION: does the synthetic `rx_weekly` feed stand for projected (open) panel data or observed (closed) claims? Panel coverage is reported per cut (for example 0.656 for New England, 2026-05-04), which suggests a panel (open item DP-1)] | `data/agent_visible/README.md` |
| Granularity | Week × territory × plan × specialty × product for Rx; access by plan and month; promotion and inventory by week × territory × product. Rep-level data is aggregated inside the tools; no line identifies a rep. No patient-level data | `data/agent_visible/README.md`; Briefing §5.4 |
| Time | Weekly brand tracking (panel cadence), two years of history for baselines | Briefing §5.1 |
| Cost and rights | Synthetic data only: no licence, nothing to re-identify, model training allowed. A real deployment would need each of these answered per vendor, and a data-use review per model provider (System S14) | Shared constitution Principle VI; System S14 |
