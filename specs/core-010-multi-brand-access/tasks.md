# Tasks — core-010

- [x] Record the workspace/competitor policy, role/grant distinction and rollout scope.
- [x] Confirm BXA/BXC governed reference figures and shared flagged cuts.
- [x] Parameterize scripted scope, triage, queries, checks, projections, charts and memo.
- [x] Bind non-BXA IDs and reviewed plans to brand, retaining BXA compatibility.
- [x] Split validated account grants from persona roles; add Keycloak/dev account pairs.
- [x] Return authorized release brands and engine capabilities; enforce grants before execution.
- [x] Reuse stored-brand checks for briefs, approval, threads, shared links and votes.
- [x] Guard agent submission, job ownership/scope, worker execution and result admission.
- [x] Require BXA for Forecast; retain BXC brand metadata in Feedback Review proposals.
- [x] Wire brand-aware Overview and selection; clear old scope/evidence and ignore late responses.
- [x] Add focused authorization/numeric/evidence tests and the API CI entry.
- [x] Pass frontend type/build checks and desktop/phone browser walkthroughs, including BXC follow-ups.
- [x] Pass the BXA scripted evaluation gate against unchanged main.
- [x] Pass the complete regression run: 380 tests and 10 subtests; runtime/eval isolation checks also pass.

## Local verification

- DuckDB load/check: all fourteen tables verified; expected missing/duplicate feed artifacts retained.
- Backend: `uv run --no-sync pytest tests -q` — 380 passed, 10 subtests passed.
- Frontend: TypeScript and standalone Vite production build passed.
- Signed-in browser: BXC triage/generation, own numeric evidence and scripted follow-ups, analyst approval, authorized leadership summary, blocked BXA-only accounts, preserved week, stale-response isolation, and 320px/390px layouts passed.

## Scripted evaluation

Base: `5b8dfb7fa7eec05b2ab943a3816f655946af98c4`.

- Baseline: `0e8780cd76c24eb5b30c515b6f4d313e`.
- Candidate: `b972c12df4ea46ad8c7a56b337228bf0`.
- Thirty Briefing cases; no run errors. All seven gated checks remain 1.000: must-not-say, governed terms, no individual rep, claim reconciliation, traced numbers, resolving links, and memo sections. Golden-number recall remains 0.525 (report-only).

## After merge — hosted rollout

The code change does not modify a running Keycloak realm. Apply the explicit account grants with Michael **before the merge triggers app deployment**, then sign out/in and repeat the same-role/different-grant UAT walkthrough in [MULTI_BRAND_UAT.md](../../docs/MULTI_BRAND_UAT.md). Record the hosted revision, allowed BXC brief and denied BXC request. BXC agent/Forecast support and immediate session revocation remain outside this release.
