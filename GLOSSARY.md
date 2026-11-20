# PharmAgentics

A first-pass forensic analyst for pharma brand performance. This glossary covers the weekly briefing; the forecast lane adds its own terms.

## Weekly briefing

**Brief**:
The weekly brand-performance memo for one brand, territory and reporting week, in a fixed outline of sections.
_Avoid_: report, briefing document, output

**Section**:
One numbered part of a brief's fixed outline: Bottom line, The numbers, What changed and why, What the data can't tell us, Next checks, Appendix.
_Avoid_: block, card, part

**Story**:
One material change the brief explains, with the checks run on it, a confidence level and an owner. Stories live in "What changed and why".
_Avoid_: finding, insight, driver (a driver is what a story may name)

**Driver**:
The cause a story names for a change, such as an access change, a supply problem or competitive intelligence on a rival launch.
_Avoid_: reason, root cause

**Claim**:
A number in a brief, filled in by code from a stored query, never written by a model.
_Avoid_: stat, figure, metric value

**Evidence table**:
The rows behind a section's claims, with the query that produced them. Analysts see it; leaders do not.
_Avoid_: raw data, backing data

**Like-for-like**:
A comparison that uses only territories whose feed passed its checks in every week compared.
_Avoid_: comparable, same-store

**Panel coverage**:
The share of a territory's expected prescription records that arrived in a given week.
_Avoid_: completeness, capture rate

**Projected national**:
National TRx built territory by territory: each territory's observed TRx divided by its panel coverage, summed.
_Avoid_: total, national actual

**Estimated territory**:
A territory whose coverage is too low to project, filled from its own recent share of national and labelled as estimated.
_Avoid_: imputed, interpolated

**Withheld cut**:
A territory or week whose data failed its checks, so no story or driver is given for it.
_Avoid_: excluded, dropped, suppressed

**Follow-up**:
A question an analyst asks about a brief after it is written, answered with new claims and kept in the brief's thread.
_Avoid_: chat message, prompt

**Thread**:
The follow-ups and answers attached to one brief. A thread is never part of what is approved.
_Avoid_: conversation, session

**Saved thread**:
A thread an analyst chose to keep. Only saved threads are shared with other analysts and reviewed for lessons; unsaved threads expire.
_Avoid_: bookmarked chat, pinned conversation

**Lesson**:
A short, number-free piece of guidance learned from feedback, such as which check to run first for an access question.
_Avoid_: tip, rule, playbook note

**Knowledge base**:
The versioned set of approved lessons the agents read.
_Avoid_: playbook, memory, notes
