# Data model: brief-003 slice 1

## Projection row (`reporting.v_rx_projection`)

One row per week, territory and product, for every cut the feed gate knows (`v_feed_health` × products).

| Field | Type | Meaning |
| :- | :- | :- |
| `week_start` | DATE | Week |
| `territory_id` | VARCHAR | Territory (the projection stratum) |
| `product_id` | VARCHAR | BXA, BXC, BXD, BXE |
| `health_status` | VARCHAR | PASS or FLAG, from `v_feed_health` |
| `flag_reasons` | VARCHAR | `;`-joined reasons, from `v_feed_health` |
| `panel_coverage_ratio` | DOUBLE | Share of expected records that arrived |
| `basis` | VARCHAR | `observed`, `projected` or `estimated` (research R2) |
| `observed_trx` | DOUBLE | Sum of TRx as delivered; NULL when `basis = 'estimated'` |
| `projected_trx` | DOUBLE | `observed_trx / panel_coverage_ratio`; NULL when estimated |

Rules: `basis = 'observed'` iff PASS. `projected` iff FLAG, every reason in the completeness set, and coverage ≥ 0.5. Otherwise `estimated`. Estimated values are not in the view; they depend on the target week (R3, R4) and are computed in the claim's SQL.

## Projection (Python, `tools/projection.py`)

Built once per run from the Period.

| Field | Meaning |
| :- | :- |
| `national` | Claim token: average weekly projected national BXA TRx over `Period.weeks`; None when no week can be reported |
| `rows` | One per territory: `territory`, `token` (average weekly TRx), `basis` (worst basis across the weeks: estimated > projected > observed), `weeks` (week → basis for non-observed weeks), `observed` and `coverage` tokens for a single projected week |
| `projected` / `estimated` | Territories with that basis in any week of the period |

## Memo (Python, `tools/memo.py`)

| Entity | Fields |
| :- | :- |
| `Section` | `number` ("1" to "6", "3.1" …), `title`, `lines` (code template lines with tokens), `prose` (writer or template prose with tokens, may be empty) |
| `StoryBlock` | `id` (`territory:PACIFIC`, `competitor:BXE` …), `title`, `lines` (head, checks, closing confidence; no "Next:"), `prose` |
| `NextCheck` | `subject`, `action`, `owner`, `decision` |
| `MemoParts` | `title` lines, `bottom_line` lines, `numbers` lines, `stories` (StoryBlocks), `story_notes` (left out, dropped, routine, calendar), `limits` lines, `next_checks`, `appendix` lines, `answer` prose |
| Output | `template` (one string with `## ` headings and `{cN}` tokens) and `sections` (list of Section) |

State: parts are filled in stage order (1–3 before the investigation; §1 least-sure and §5 after it; writer prose last). Composition is pure: same parts, same template.

## Envelope additions (`eval/harness/envelope.py`)

`sections: list[dict] | None`, each `{number, title, text, prose, claims}`, where `text` and `prose` are rendered and `claims` indexes the envelope's `claims`. Optional; scorers ignore it.

## Relationships

`Period` → `Projection` (one per run) → claims in §1 and §2. `StoryBlock` → `NextCheck` (one per story). Withheld cuts in `Period.status` → §1 warning, §4 detail, §5 re-run check.
