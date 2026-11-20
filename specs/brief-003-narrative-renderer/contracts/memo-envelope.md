# Contract: the memo in the answer envelope

Both `briefing_scripted` and `briefing_agent` return this. `eval/harness/envelope.py` validates it.

## `answer` (flattened text, read by the scorers)

```text
Brief for week of 2026-05-04. Product: BXA.
## Bottom line
<data warning, if any cut in the period is withheld>
<restatement note, if an earlier week was restated>
<projected national>
<like-for-like change, with its territory count>
<brand share of the market basket>
<the number we are least sure of>
<writer's answer (agent only)>
## The numbers
<projected national table: one line per territory, projected and estimated rows labelled>
<KPI lines: like-for-like, week over week, headline artifact, calendar effect>
<restatements: old, new, date, reason>
## What changed and why
Story one: <head>
<writer's sentence (agent only)>
Checked, in this order:
- <check>
Confidence: <level>. <driver or abstention>
Story two: ...
<left out / considered and dropped / routine / calendar line>
## What the data can't tell us
<data health: gate detail per withheld cut>
<withheld focus territory>
<how projected and estimated territories were built, when any>
<calendar weeks left out>
## Next checks
- <subject>: <action>. Owner: <function>. Unlocks: <decision>.
## Appendix
<method: like-for-like rule, projection rule>
<data version>
<glossary of the terms used>
```

Rules:

- Headings carry no digits. Every digit elsewhere is a filled claim, an ISO date or an identifier.
- Every heading appears in every brief, in this order. An empty section says why ("No material change was found …", "Nothing in this period limits the figures above.").
- The outside-release answer is a single line and has no sections.

## `sections` (structured, optional)

```json
[{"number": "1", "title": "Bottom line", "text": "…", "prose": "…", "claims": [0, 1, 2]},
 {"number": "3.1", "title": "Pacific", "text": "…", "prose": "…", "claims": [9, 10]}]
```

`text` and `prose` are rendered (no tokens). `claims` indexes the envelope's `claims`. Story subsections follow §3 in order. Slice 2 adds `chart` and `evidence`.

## Leadership view

`views.executive_summary(answer)` returns the title, §1, §2, §3 without "Checked, in this order" lists and the "Considered and dropped" line, and §5. It drops §4 and §6.
