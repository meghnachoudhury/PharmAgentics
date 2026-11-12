# SoT: source-of-truth drops

The masters are the Google Docs and PDFs in the Drive folder **Consolidated 10/22**. Each time they change, export the folder and put the export here as one dated subfolder, exactly as Drive gave it. The newest folder is the current source of truth.

Drops are git-ignored, so binaries stay out of the repository; this README and `check.py` are committed. Spec Kit never reads the drops: it reads the reviewed Markdown copies in [`docs/planning/`](../docs/planning/README.md).

## When a new drop lands

1. Put the export in `SoT/`. A `drive-download-…` folder name works; renaming it to `YYYY-MM-DD` is clearer.
2. Run `uv run python SoT/check.py`. It refuses the drop if any file looks like the answer key or held-out parameters, lists what changed since the previous drop, and shows the lines that differ from each copy in `docs/planning/`.
3. Refresh the changed copies in `docs/planning/`.
4. Update the specs that cite changed items (pack first, then specs). A changed user story also needs its golden case updated and a line in [`eval/golden/CHANGELOG.md`](../eval/golden/CHANGELOG.md).
5. Add a row to the log below.

Never put the answer key, the generator, the true pre-artifact data or held-out parameters in a drop. They live outside the repository (constitution Principle III).

## Log

| Drop | Files | What changed | Follow-up |
| :- | :- | :- | :- |
| 2026-10-29 | 7: Proposal; Briefing personas and evaluation pack; Forecast personas and eval design (Sienna); System Architecture; user stories; system diagram | First drop. The `docs/planning/` copies matched; one diagram caption added to the System Architecture copy. The Proposal and the Forecast eval design stay uncopied (cited by ID). | None |
| 2026-11-11 | 8: the seven above, unchanged, plus `Five-question triage (data plan).png` (course slide, added by Michael) | New file only; `check.py` passed. Copied as [`docs/planning/data-plan-triage.md`](../docs/planning/data-plan-triage.md): the slide, how it differs from the stage-4 triage, and the Briefing lane's data plan | Open item DP-1 (projected or observed Rx feed). No spec or golden case changes |
