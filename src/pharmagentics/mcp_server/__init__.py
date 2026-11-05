"""PharmAgentics MCP server: the shared deterministic tools as MCP tools (core-004 FR-015, Proposed).

Any MCP client can use it unchanged: the Briefing low-code agent, a Forecast agent, Claude Desktop or
Claude Code. See README.md in this folder for the tool list and how a lane adds its own tools.
"""
from .server import AGENT_TOOLS, ADMIN_TOOLS, RunSession, build_server

__all__ = ["AGENT_TOOLS", "ADMIN_TOOLS", "RunSession", "build_server"]
