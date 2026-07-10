"""
MCP tool definition for search_kidney_guidelines.

Keeps tool schema and dispatch logic separate from RAG internals.
"""

from __future__ import annotations

import json
import sys
import os

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rag.kidney_rag import search_kidney_guidelines

TOOL_NAME = "search_kidney_guidelines"

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Search kidney clinical guidelines (KDIGO) using semantic similarity. "
        "Returns the most relevant passages with source file and page citations."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Clinical question or topic to search for.",
            },
            "k": {
                "type": "integer",
                "description": "Number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}


def execute(arguments: dict) -> dict:
    """Run the RAG search and return structured results."""
    query = arguments["query"]
    k = int(arguments.get("k", 5))
    return search_kidney_guidelines(query, k=k)
