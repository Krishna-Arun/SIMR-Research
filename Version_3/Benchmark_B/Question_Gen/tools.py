"""
Bridge between the PubMed MCP server and the agentic loop.

- catalog_text(): compact human-readable tool catalog for the ReAct prompt.
- ToolDispatcher: query-guard (no PHI/identifiers/raw values) -> mcp_client.call ->
  trimmed observation. Tracks consecutive failures so the loop can trip a breaker.

Kept small on purpose: we expose only the PubMed tools that help ground a
citation, and we never send patient specifics to an external service.
"""
from __future__ import annotations

import re

from mcp_client import MCPClient, MCPError

# Only the discovery/retrieval tools useful for grounding a citation.
ENABLED = {
    "search_articles", "advanced_search", "search_by_mesh_terms",
    "get_abstract", "get_article_details", "validate_pmid",
}

# Cheap guard: block obvious patient specifics leaking into an external query.
_BLOCK = re.compile(r"\b(subject_id|hadm_id|mrn|\d{6,}|\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


class QueryGuardError(ValueError):
    pass


def guard_args(args: dict) -> dict:
    """Reject tool args that look like they carry identifiers/dates/raw values."""
    for k, v in args.items():
        if isinstance(v, str) and _BLOCK.search(v):
            raise QueryGuardError(
                f"arg '{k}' looks like it contains a patient identifier/date/raw value; "
                "query PubMed with GENERAL clinical concepts only")
    return args


def catalog_text(mcp_tools: list[dict]) -> str:
    lines = []
    for t in mcp_tools:
        if t["name"] not in ENABLED:
            continue
        schema = t.get("inputSchema", {}) or {}
        props = schema.get("properties", {})
        req = set(schema.get("required", []))
        sig = ", ".join(f"{k}{'*' if k in req else ''}" for k in props)
        lines.append(f"- {t['name']}({sig}): {t.get('description','')[:140]}")
    return "\n".join(lines)


def merged_catalog(clients) -> str:
    """Human-readable catalog across several MCP clients (all tools, no whitelist)."""
    lines = []
    for c in clients:
        for t in c.tools:
            schema = t.get("inputSchema", {}) or {}
            props = schema.get("properties", {})
            req = set(schema.get("required", []))
            sig = ", ".join(f"{k}{'*' if k in req else ''}" for k in props)
            lines.append(f"- {t['name']}({sig}): {t.get('description','')[:140]}")
    return "\n".join(lines)


class MultiDispatcher:
    """Routes tool calls across multiple MCP clients (e.g. supplementals + PubMed).

    Applies the PHI query-guard only to PubMed tools (external); supplementals
    stay local so their args are not guarded.
    """
    def __init__(self, clients, max_chars: int = 2000, max_failures: int = 4):
        self.clients = clients
        self.route = {}
        self.tools = []
        for c in clients:
            for t in c.tools:
                self.route[t["name"]] = c
                self.tools.append(t)
        self.max_chars = max_chars
        self.max_failures = max_failures
        self.consecutive_failures = 0

    @property
    def tripped(self) -> bool:
        return self.consecutive_failures >= self.max_failures

    def dispatch(self, name: str, args: dict) -> str:
        client = self.route.get(name)
        if client is None:
            return f"ERROR: unknown tool '{name}'. Available: {sorted(self.route)}"
        try:
            if name in ENABLED:            # PubMed tools -> guard args (external)
                guard_args(args)
            out = client.call(name, args)
            self.consecutive_failures = 0
            return out[:self.max_chars]
        except QueryGuardError as e:
            return f"ERROR (query blocked): {e}"
        except MCPError as e:
            self.consecutive_failures += 1
            return f"ERROR (tool failed): {e}"


class ToolDispatcher:
    def __init__(self, mcp: MCPClient, max_chars: int = 1800, max_failures: int = 3):
        self.mcp = mcp
        self.max_chars = max_chars
        self.max_failures = max_failures
        self.consecutive_failures = 0

    @property
    def tripped(self) -> bool:
        return self.consecutive_failures >= self.max_failures

    def dispatch(self, name: str, args: dict) -> str:
        if name not in ENABLED:
            return f"ERROR: tool '{name}' is not available. Choose from: {sorted(ENABLED)}"
        try:
            guard_args(args)
            out = self.mcp.call(name, args)
            self.consecutive_failures = 0
            return out[:self.max_chars]
        except QueryGuardError as e:
            return f"ERROR (query blocked): {e}"      # not a server failure; don't count it
        except MCPError as e:
            self.consecutive_failures += 1
            return f"ERROR (tool failed): {e}"
