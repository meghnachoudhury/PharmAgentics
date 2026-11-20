# Feature Specification: Per-user brand access

**Spec ID**: core-010-multi-brand-access (shared)
**Branch**: feature/multi-brand-access
**Created**: 2026-11-20
**Scope**: BXC (Lipidara) scripted Weekly Briefing; BXA workflows retained.

## Clarifications

- Role controls actions and views; account-level brand grants independently control which brand workspaces and saved records those actions apply to. Classification remains a label (core-009 US1).
- Competitor policy: a grant protects a dedicated brand workspace, its investigations, and saved records. Named aggregate competitor TRx and shares in the four-brand market basket remain permitted context in an authorized workspace, including their supporting aggregate evidence. A BXA grant does not grant the BXC workspace. Existing BXA briefs need no competitor redaction under this policy.
- The server intersects the release catalog, implemented engines, and account grants. BXA supports scripted and agent Briefing. BXC supports scripted Briefing only. Forecast remains BXA-only because no BXC forecast-versus-actual series exists.
- Keycloak realm roles `brand-bxa` and `brand-bxc` are account grants, separate from persona roles. No grant means no brands. The tester persona switch retains its account grants.
- Grants are captured at validated sign-in and last for the existing session lifetime. Grant changes require sign-out/sign-in. Immediate active-session revocation is not implemented by this feature.
- Shared feed-health rules, projection assumptions and generic driver thresholds apply to both brands. The Metacora comparison continues to use BXE as competitor and the selected brand as the primary share. This does not add a calibrated BXC agent or forecast model.

## User stories and acceptance criteria

### US1 — A brand-specific scripted brief

An analyst granted BXA and BXC can select Lipidara, review its triage, generate a BXC memo with BXC claims, evidence and charts, and approve it. A granted Director sees its approved executive summary without analyst evidence or traces; drafts remain hidden.

- Reference: `2026-06-08 / PACIFIC`, governed weekly KPIs: BXA TRx/NRx/NBRx = 464/96/49; BXC = 626/140/83. Assert numeric results and rerun evidence, not just labels.
- `2026-05-04 / NEW_ENGLAND` is withheld for both brands; projections are qualified assumptions and no driver is assigned to the withheld cut.
- BXA and BXC with identical dates, territory and question have distinct IDs and plans. Cross-brand reviewed plans fail. Existing BXA IDs, approvals and shared links remain compatible.

### US2 — Account grants enforce access everywhere

Two analysts with the same persona but different grants prove per-user authorization. Analyst A and Director A have BXA/BXC; Analyst B and Director B have only BXA.

- Context returns each user's authorized brand catalog and per-brand engines; zero grants returns an empty list and a clear UI state.
- BXA-only users receive 403 before engine execution for BXC Overview, triage, generation and agent submission. BXC agent requests are rejected even for granted users.
- Lists exclude ungranted saved records. Direct reads, reviews, threads/shared links and votes return 404 without response text or writes. Lookup uses the stored brand, never a caller's override.
- Agent jobs require brand support, requester ownership and matching scope when referencing triage jobs. Result admission checks its brand; polling cannot expose another user's or an ungranted brand's job.
- BXA Forecast routes and feedback require a BXA grant. Feedback Review proposals carry/resolve brand and require the tester's corresponding grant.

### US3 — A consistent authorized UI

- Brand choices and engine capabilities come from the API. Labels use Cardiovela (BXA) and Lipidara (BXC).
- Switching brand clears the previous plan, report, error, follow-up context and evidence drawer. Late responses cannot restore the previous brand's state.
- Overview, approved rows, analyst reports and leadership summaries identify their brand. Switching to BXC selects Scripted; switching back preserves BXA engine availability.

## Verification and rollout

Run the focused brand-access and existing API/tool suites, frontend type/build checks, signed-in browser walkthroughs, and the Briefing scripted evaluation gate against unchanged main. Do not merge on regressions (B-VII).

The PR updates the realm template, not the running Keycloak server. Coordinate the live grant rollout with Michael: explicitly grant existing UAT users BXA before deploying the enforcing app, add BXC only to selected accounts, then sign out/in and repeat the same-role/different-grant walkthrough in UAT. Record one allowed BXC run and one denied BXC request. Do not deploy or change live users as part of this code change.
