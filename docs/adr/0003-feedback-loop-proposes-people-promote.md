# The feedback loop proposes lessons and cases; people promote them

Votes, comments and saved threads feed `python -m eval improve`, which drafts lessons for the knowledge base and draft golden cases, reruns the flagged questions with each draft lesson, and runs `eval gate`. A lesson is "confident" only when the rerun no longer shows the reported problem, the gate shows no regression, and the lesson holds no numbers or unapproved terms; everything else is flagged to a reviewer with its reason. Either way a person approves every promotion, which opens a pull request into the versioned knowledge base. The loop never edits code or prompts (those become issues), and agents never read past threads directly, so old numbers and mistakes cannot leak into new answers and eval results cannot drift without a reviewed change.

## Consequences

The improver lives in `eval/` and the knowledge base outside it (`agents/brand-briefing/knowledge/`), so agents keep their rule of never reading `eval/`. Postgres testing is a named open item for later, not part of this loop.
