#!/usr/bin/env python3
"""
keratin - Main entry point

Convenience wrapper to start the keratin MCP server.
Prefer the CLI entry point: `keratin` (after pip install keratin).
"""

from rhino_mcp.server import main

if __name__ == "__main__":
    main() 