from __future__ import annotations

import argparse
from pathlib import Path

from agentic_research.mcp_server import create_mcp_server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TradeBot read-only research MCP server")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--transport", choices=("stdio", "sse", "streamable-http"), default="stdio")
    args = parser.parse_args()
    server = create_mcp_server(Path(args.repo_root).resolve())
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
