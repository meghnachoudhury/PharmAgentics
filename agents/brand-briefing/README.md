# Brand-Performance Briefing Agent

The Briefing lane (Michael, Meghna): a weekly brand-performance brief that validates the data, finds material changes, tests competing explanations, and writes a brief in which every number is traceable.

## Built

`briefing_baseline/` is the **scripted baseline** (Evaluation Pack §6): a fixed pipeline with a fixed order of checks and a template brief. No model. Every number is a claim token filled by code from a stored SQL query, so the eval harness can re-run each one.

| Stage | Where |
| :- | :- |
| 1 load and pin; 2 validation gate; 3a competitive intelligence; 4a investigation; 5 narrative; 6 verification | `briefing_baseline/pipeline.py` |
| Question to weeks and territory | `src/pharmagentics/tools/window.py` (shared with the Forecast lane) |
| Driver checks (access, promotion, supply, competitor, data) and confidence rule | `src/pharmagentics/tools/checks.py` (shared) |
| Governed read-only data access, evidence items, claim tokens | `src/pharmagentics/tools/registry.py` (shared) |
| Stage 1 to 3 steps, story head, Metacora status | `src/pharmagentics/tools/stages.py` (shared; the MCP tools call the same functions) |

Run it through the eval harness: `uv run python -m eval run --system briefing_scripted --lane briefing`.

`briefing_lowcode/` is the **low-code build** (Briefing Architecture §14, build 2): Microsoft Agent Framework's Magentic-One orchestration at its defaults. The framework's manager plans, keeps the task and progress ledgers, picks who acts next and replans when it stalls. Its two specialists, Data Forensics and the Driver Investigator, call the shared [PharmAgentics MCP server](../../src/pharmagentics/mcp_server/README.md), each limited to its own tool group. `team.yaml` and `prompts/` are the whole configuration. `team.py` wires them to the framework and keeps the number rules in code: the server pins the run, digits outside claim tokens get one revision, and code fills the tokens. A run that hits the round cap still ends with a brief, marked capped.

```powershell
uv run python -m eval run --system briefing_lowcode --lane briefing                         # local qwen3:4b-instruct
uv run python -m eval run --system briefing_lowcode --lane briefing --model gemini:         # GEMINI_MODEL from .env
```

Not built yet: the custom Magentic agent (build 3, spec brief-002), human review (stage 7).

Agent code never imports `eval/`; the harness imports it.
