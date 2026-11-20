# Tasks: the feedback loop (core-008 FR-019 to FR-022; memo slice 5)

- [X] T001 [FR-022] agents/brand-briefing/knowledge/lessons.yaml (empty) and agents/brand-briefing/briefing_agent/lessons.py (approved lessons, trial lessons for eval reruns); the writer prompt gets them; config_version includes the file
- [X] T002 [FR-019, FR-020] eval/harness/improve.py: collect new votes and saved threads, draft lessons (Haiku), code checks, rerun with the lesson, agent reviewer, optional gate, draft cases from upvotes, write proposals
- [X] T003 [FR-019] `python -m eval improve` and `python -m eval promote` in eval/__main__.py
- [X] T004 [FR-021] src/pharmagentics/api/review.py (tester admin only, no UAT event) mounted in app.py
- [X] T005 [FR-021] eval/harness/promote.py: approved lessons into lessons.yaml, approved cases into eval/candidates/, proposals marked promoted, git commands printed
- [X] T006 [FR-021] frontend/figma-make/src/FeedbackReview.tsx and agent/reviewApi.ts; shown on the Evaluation page for the tester admin
- [X] T007 tests/test_feedback_loop.py: code checks, confident and flagged rules, proposals written, promote output, API access, agents read approved lessons only
- [ ] T008 Gate both engines against slice 4 (`88e13b759f5c`, `66920e2b0f8a`); commit by path
