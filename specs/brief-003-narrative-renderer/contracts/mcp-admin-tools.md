# Contract: MCP admin tools for the memo

Admin tools are called by code (the agent's runner), never offered to a model (`ADMIN_TOOLS`). All text uses claim tokens from the run's Registry.

## `brief_sections() -> JSON`

Called once, right after `open_run`, before the investigation.

| Key | Type | Meaning |
| :- | :- | :- |
| `title` | list[str] | "Brief for … Product: BXA." and the period note |
| `numbers` | list[str] | §2 lines: projection table, KPI lines, restatements |
| `limits` | list[str] | §4 lines: data health, withheld focus, projection method, calendar note |
| `appendix` | list[str] | §6 lines |
| `calendar` | bool | Calendar mode: §3 opens no story |
| `withheld_focus` | str \| null | Kept for the writer's view |

The old keys `header`, `data_health` and `kpis` are removed; only `briefing_agent` used them.

## `story_section(territory, n) -> str`

Unchanged name and arguments. The closing line no longer carries "Next: …" (moved to §5).

## `memo_close(competitor: bool) -> JSON` (new)

Called once after the investigation and before `export_run`, so its claims are exported.

| Key | Type | Meaning |
| :- | :- | :- |
| `bottom_line` | list[str] | §1 code lines in FR-021 order, least-sure by research R8 over the stories this session closed |
| `next_checks` | list[str] | §5 lines, one per story closed, withheld cut and (if `competitor`) the Metacora story |

## Agent tools

Unchanged. `story_confidence` still returns "Next: …" to the agents; only the brief's text moves it to §5.
