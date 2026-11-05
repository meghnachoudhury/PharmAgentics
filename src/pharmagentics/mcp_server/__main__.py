"""Run the PharmAgentics MCP server over stdio: `uv run python -m pharmagentics.mcp_server [--db PATH]`."""
from __future__ import annotations

import argparse

from pharmagentics.tools import DEFAULT_DB

from .server import build_server


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m pharmagentics.mcp_server")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="DuckDB file built from data/agent_visible/")
    ap.add_argument("--legend", action="store_true", help="append each token's value to tool text")
    args = ap.parse_args()
    build_server(args.db, legend=args.legend).run("stdio")


if __name__ == "__main__":
    main()
