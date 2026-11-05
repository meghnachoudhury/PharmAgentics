# PharmAgentics MCP server

The shared deterministic tools (`src/pharmagentics/tools/`) served over the Model Context Protocol, so any agent framework or MCP client can call them without changes (core-004 FR-015). Status: **Proposed** as the shared tool interface (System Architecture S9). The Briefing low-code agent uses it today. Alvin and Sienna decide whether the Forecast lane adopts it.

## Run it

```powershell
uv run python -m pharmagentics.mcp_server            # stdio; --db PATH for another DuckDB file
```

Any MCP client that starts a stdio server can use it. For a client outside the repo, give it the command `uv` with the arguments `run --directory <repo path> python -m pharmagentics.mcp_server`. In an interactive client such as Claude Desktop, the model calls `open_run` itself.

From Python with Microsoft Agent Framework, code opens and exports the run, and the agents get only their tool group:

```python
from agent_framework import MCPStdioTool
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

server = StdioServerParameters(command="uv", args=["run", "python", "-m", "pharmagentics.mcp_server"])
async with Client(server) as mcp:
    await mcp.call_tool("open_run", {"question": question})
    async with MCPStdioTool(name="pharmagentics", mcp_client=mcp,
                            allowed_tools=["feed_health", "national_kpis"]) as tools:
        ...  # give `tools` to an Agent and run it
    run = await mcp.call_tool("export_run", {})  # claims and evidence for the answer envelope
```

`agents/brand-briefing/briefing_lowcode/team.py` is the full version.

## How a run works

1. **The caller (code) calls `open_run(question)`.** The server resolves the weeks, the baseline weeks and any territory the question names, and pins one data version. One server process serves one run at a time; calling `open_run` again starts a new run.
2. **Agents call the agent tools in any order.** Each call adds evidence items and claim tokens to the run's Registry.
3. **The caller calls `export_run()`.** It returns the claims, evidence items, verdicts and the call log as JSON, and the caller builds its answer envelope from them. Agents never see the admin tools.

Every number in a tool's text is a claim token such as `{c7}`. The model writes tokens and code fills them in (Briefing B-III). `--legend` (or `build_server(legend=True)`) also appends each token's value, for models that need the size. It is off by default because the 4B local model copied the legend's values into its prose. Each driver check also reports the story's confidence so far, computed by code, and `story_confidence` closes the story. Verdicts and confidence are computed by code. The model chooses which tool to call, for which territory, and when to stop. No tool accepts SQL or free text, only a territory ID or nothing (brief-002 FR-020).

## Tools

| Group | Tool | Wraps |
| :- | :- | :- |
| admin | `open_run`, `export_run` | `tools.stages.resolve`, the Registry |
| `data_forensics` | `feed_health`, `restatements`, `national_kpis`, `check_data` | `tools.stages`, `tools.checks` |
| `driver_investigator` | `screen_territories`, `territory_change`, `check_access`, `check_promotion`, `check_supply`, `check_competitor`, `competitor_status`, `story_confidence` | `tools.stages`, `tools.checks` |

The groups (`AGENT_TOOLS` in `server.py`) are the Briefing lane's two specialists. The Forecast lane could reuse the period, `feed_health`, `restatements`, `check_access`, `check_supply`, `check_competitor` and `competitor_status` as they are.

## Adding a lane's tools

1. Put the logic in plain code under `src/pharmagentics/tools/`, with every number going through `Registry.claim`.
2. Add a method on `RunSession` that calls it and returns `self._out(text)`.
3. Register it in `build_server` with `@server.tool(structured_output=False)`. The docstring is the description the model reads.
4. Add it to a group in `AGENT_TOOLS`, such as a new `forecast_*` group.
5. Add a test in `tests/test_mcp_server.py`: no digit outside tokens, and the same values as the plain code.

## Rules it keeps

- Read-only and governed: every query goes through `Registry`, which allows only SELECTs on the allowlisted views (constitution Principle I).
- No model inside: tools are plain code (guardrail rule 1). `tests/test_mcp_server.py` checks this.
- Never reads `eval/` or the answer key (`eval/tests/test_isolation.py` scans `src/`).
