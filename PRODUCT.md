# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Commercial Analyst (primary).** Works on a pharma brand team. Each week they generate the brand-performance brief, or a forecast-versus-actual explanation, check the evidence behind each figure, and approve it. Their job is to review, not to rebuild the numbers.
- **Brand Director and Brand Manager (secondary).** Read the executive summaries an analyst has approved, and the Brand Manager approves Forecast explanations. They never see evidence or source queries.
- **Today:** a Columbia course capstone (IEOR4573E, Fall 2026) in user acceptance testing on synthetic data. Testers are the team and the course mentor.

## Product Purpose

A multi-agent first-pass forensic analyst for pharma brand performance, with two use cases: the Weekly Brand-Performance Briefing and the Forecast Explanation. It does the checking (data health, drivers, comparisons) so the analyst starts from a traceable draft. Success is an analyst who trusts the draft enough to review and approve it quickly, and a leader who gets a short summary they can act on.

## Positioning

Every figure comes from a governed, versioned SQL query and is filled in by code, never written by a language model. Each claim links to its evidence. Nothing reaches a leader until an analyst approves it.

## Operating Context

- Weekly rhythm: pick a brand, territory and reporting week (or a forecast window), generate, review the triage plan, read the brief, open the evidence behind any number, approve or return it.
- Two engines: a scripted baseline (instant) and an experimental agent team (slower, runs on a separate host).
- Roles come from single sign-on; the server decides each role's view. A test login can switch between the analyst and leadership views.
- Feedback is collected in the product: thumbs up or down per answer, a session rating, and a platform questionnaire.

## Capabilities and Constraints

- Synthetic data only. Data classification per tab (public, proprietary, confidential, sensitive) is shown as a label; enforcement by level is not built yet.
- Leaders never see evidence, claims or SQL.
- Never identify an individual rep.
- Say "competitive intelligence", never "surveillance". Use "new patients" only for NBRx.
- Free-form questions are limited to the agent engine; charts are not built.

## Brand Commitments

- Name: PharmAgentics. Mark: "Pa", set like a prescription sign (Rx), with the "a" lowered like a subscript.
- Users never see testing scaffolding: no "UAT" names, persona codes (P1, CA) or internal plumbing in the interface.
- Dark interface only (decided by the product owner, 2026-11-19).

## Evidence on Hand

- The governed synthetic release in `data/agent_visible/` and the golden evaluation set in `eval/` (42 cases).
- No customers, testimonials or benchmarks exist; do not invent them.

## Product Principles

1. Traceable before persuasive: a number without its source is not shown as a fact.
2. The analyst decides: the product drafts and checks; a person approves what leaders see.
3. Say what is uncertain: withheld cuts, paused attributions and data-quality problems are shown, never hidden.
4. Quiet tools: the interface recedes so the evidence and the decision lead.

## Accessibility & Inclusion

- WCAG 2.2 AA contrast and keyboard access.
- Desktop first, usable on a phone.
