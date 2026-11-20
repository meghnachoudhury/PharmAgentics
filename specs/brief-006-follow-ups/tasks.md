# Tasks: Follow-ups and Threads

**Input**: `specs/brief-006-follow-ups/` (spec.md, plan.md)

## Slice 3: threads, the message bar, scripted follow-ups

- [X] T001 [US1] Scripted follow-up rules in src/pharmagentics/tools/followup.py (section reference, out of scope with an offer, no driver for a projected or estimated cut, "not in this brief" for new numbers, else restate the section with its claims)
- [X] T002 [US1] tests/test_followup.py: each rule on real briefs (2026-06-08 Pacific, 2026-05-04 New England), no digit outside a claim value or date, every cited section exists
- [X] T003 [US4] Thread store and routes in src/pharmagentics/api/threads.py (my thread, ask, save, shared, continue; 20-turn cap; lazy 30-day purge; analysts only, others 404)
- [X] T004 [US4] Mount the router in src/pharmagentics/api/app.py (one line)
- [X] T005 [US4] Turn references `b-<id>:t<n>` for votes in src/pharmagentics/api/feedback.py
- [X] T006 [US4] tests/test_threads.py: owner isolation, leaders 404, cap, save and share, continue, purge, vote on a turn
- [X] T007 [US2] UI: frontend/figma-make/src/agent/threadApi.ts and MessageBar.tsx; "Ask about this" in Memo.tsx; bar mounted in the analyst views in App.tsx
- [X] T008 [US2] Real-app check in headless Chrome: ask about §3.1, a suggestion, an out-of-scope question, save and open the share link; the director sees no bar
- [ ] T009 Gate both engines against the slice 2 runs (no brief changes); commit by path

## Slice 4: Haiku follow-ups and two-turn cases

- [X] T010 [US1] Agent follow-up in agents/brand-briefing/briefing_agent/ (one agent, both tool sets, sections as context, 60 s, token checks and one revision)
- [X] T011 [US5] Timeout path: "Didn't finish in time; nothing was guessed", recorded as a run error, no answer stored
- [X] T012 [US1] Threads call the agent when asked (engine choice in the bar)
- [X] T013 Harness: `follow_up` in cases, two-turn predict, `sections_exist` gated check, latency median and p95 (eval/harness/)
- [X] T014 Six draft two-turn golden cases (FR-013) with SQL facts
- [X] T015 Gate both engines; commit by path

- Slice 4 gate (2026-11-20): 30 Briefing cases (24 plus FU-1 to FU-6). Scripted `88e13b759f5c` against `060132b35cc1`, exit 0; agent `66920e2b0f8a` (four workers) against `43c24bc0a892`, exit 0. Every gated check 1.000 including the new `sections_exist`; no run errors. Agent follow-up turns: p50 2.5 s, p95 19.7 s (target under 30 s, SC-005); `needed_revision` 0.133 (4 of 30 cases). Full test suite: 589 passed after the integrity test counted 48 cases.
