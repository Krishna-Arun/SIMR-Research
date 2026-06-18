#!/usr/bin/env python3
"""
Kidney MCP Server — entry point.

Starts stdio MCP server, builds the RAG index at startup,
and registers the search_kidney_guidelines tool.
"""

from __future__ import annotations

import json
import sys
import os

# Ensure sibling packages are importable regardless of cwd
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from tools.kidney_rag_tool import TOOL_NAME, TOOL_SCHEMA, execute

# ---------------------------------------------------------------------------
# Pre-build the RAG index (happens once; subsequent calls use the cache).
# ---------------------------------------------------------------------------
print("[kidney-mcp] Initialising RAG index …", file=sys.stderr, flush=True)
from rag.kidney_rag import get_rag  # noqa: E402  (import triggers build)
get_rag()
print("[kidney-mcp] RAG index ready. Starting MCP server.", file=sys.stderr, flush=True)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
app = Server("kidney-guidelines-rag")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=TOOL_SCHEMA["name"],
            description=TOOL_SCHEMA["description"],
            inputSchema=TOOL_SCHEMA["inputSchema"],
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != TOOL_NAME:
        raise ValueError(f"Unknown tool: {name}")

    result = execute(arguments)
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
