"""Bridge between the PubMed MCP server and the agentic loop.

- to_openai_tools(): convert the cached MCP tool catalog into the OpenAI `tools` schema (for native
  tool-calling) and a compact human-readable catalog (for the ReAct-JSON protocol).
- ToolDispatcher: validate -> sanitize (PHI gate) -> mcp_client.call -> compact result. Tracks a
  consecutive-failure count so the agentic loop can trip a circuit breaker.
"""
from __future__ import annotations

import json

from qgen.mcp_client import MCPClient, MCPError
from qgen.sanitizer import SanitizerError, sanitize_args

# Tools that don't help question generation / could send odd payloads — keep the surface small.
_ENABLED = {
    "search_articles", "advanced_search", "search_by_mesh_terms", "search_by_journal",
    "get_abstract", "get_article_details", "get_similar_articles", "validate_pmid",
}


def to_openai_tools(mcp_tools: list[dict]) -> list[dict]:
    out = []
    for t in mcp_tools:
        if t["name"] not in _ENABLED:
            continue
        out.append({"type": "function", "function": {
            "name": t["name"],
            "description": t.get("description", "")[:1024],
            "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
        }})
    return out


def catalog_text(mcp_tools: list[dict]) -> str:
    """Compact catalog for the ReAct prompt."""
    lines = []
    for t in mcp_tools:
        if t["name"] not in _ENABLED:
            continue
        props = (t.get("inputSchema", {}) or {}).get("properties", {})
        req = (t.get("inputSchema", {}) or {}).get("required", [])
        args = ", ".join(f"{k}{'*' if k in req else ''}" for k in props)
        lines.append(f"- {t['name']}({args}): {t.get('description','')[:140]}")
    return "\n".join(lines)


class ToolDispatcher:
    def __init__(self, cfg: dict, mcp: MCPClient):
        self.cfg = cfg
        self.mcp = mcp
        self.max_chars = 1800            # trim each observation to control context length
        self.consecutive_failures = 0
        self.max_failures = int(cfg["pubmed_mcp"].get("max_consecutive_failures", 3))

    @property
    def tripped(self) -> bool:
        return self.consecutive_failures >= self.max_failures

    def dispatch(self, name: str, args: dict, forbidden_ids: list[str] | None = None) -> str:
        if name not in _ENABLED:
            return f"TOOL_ERROR: unknown/disabled tool {name!r}. Available: {sorted(_ENABLED)}"
        try:
            args = sanitize_args(name, args or {}, forbidden_ids)
        except SanitizerError as e:
            # not a server failure — don't count toward the breaker; coach the model
            return (f"TOOL_ERROR: blocked by PHI gate ({e}). Query with GENERAL clinical concepts "
                    f"only (e.g. 'lactate sepsis prognosis guideline'), never patient ids/dates/values.")
        try:
            raw = self.mcp.call(name, args)
            self.consecutive_failures = 0
            return self._compact(raw)
        except MCPError as e:
            self.consecutive_failures += 1
            try:
                self.mcp.restart()
            except Exception:
                pass
            return f"TOOL_ERROR: PubMed call failed ({e})."

    def _compact(self, raw: str) -> str:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return raw[: self.max_chars]
        # trim article lists to PMID + title + journal to save context
        if isinstance(obj, dict) and "articles" in obj and isinstance(obj["articles"], list):
            slim = {k: obj[k] for k in ("totalResults", "returnedResults") if k in obj}
            slim["articles"] = [{"pmid": a.get("pmid"), "title": a.get("title"),
                                 "journal": a.get("journal"), "publicationDate": a.get("publicationDate")}
                                for a in obj["articles"][:8]]
            return json.dumps(slim)[: self.max_chars]
        return json.dumps(obj)[: self.max_chars]
