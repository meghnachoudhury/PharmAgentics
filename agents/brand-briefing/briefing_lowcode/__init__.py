"""Briefing lane, low-code build (Briefing Architecture §14, build 2): Magentic-One from Microsoft Agent
Framework, configured by team.yaml and prompts/, calling the shared PharmAgentics MCP server."""
from .team import answer, config_version

__all__ = ["answer", "config_version"]
