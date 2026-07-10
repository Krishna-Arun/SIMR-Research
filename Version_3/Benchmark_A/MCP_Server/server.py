#!/usr/bin/env python3
"""
Benchmark A — Supplementals MCP Server (stdio, dependency-free)

Serves each question's pre-time-zero supplemental data behind three tools so that
NO raw values ever have to be stuffed into a prompt — agents retrieve only what
they need:

  * Access_All_supplementals_no_values(question_id) — catalog: group + item_name +
    date, NO values. Must be called before any value request (gate).
  * Request_a_supplemental(question_id, category, item_name) — full value series
    for ONE named item.
  * Request_values(question_id, items=[{category,item_name},...]) — batch-fetch
    ONLY the listed items in one call. The efficient path.

Speaks minimal MCP JSON-RPC 2.0 over stdio (initialize / tools/list / tools/call),
matching Question_Gen/mcp_client.py. Pure stdlib — runs on Python 3.9 (no `mcp`
package, no FastMCP). Data source: one JSON bundle per question in
$SUPPLEMENTALS_DIR (default ./supplementals/), produced by
context_builder.to_supplemental_bundle(). Bundles hold ONLY pre-t0 data.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BUNDLE_DIR = Path(os.environ.get(
    "SUPPLEMENTALS_DIR", Path(__file__).resolve().parent / "supplementals"))

_accessed = set()
_bundle_cache = {}

_NAME_KEYS = ("item_name", "test_name", "drug", "title")
_DATE_KEYS = ("charttime", "starttime", "chartdate", "date")
_KEEP_NO_VALUE = _NAME_KEYS + _DATE_KEYS + ("category", "source", "direction", "spec_type", "icd_code")


def _load_bundle(qid):
    if qid in _bundle_cache:
        return _bundle_cache[qid]
    p = BUNDLE_DIR / f"{qid}.json"
    if not p.exists():
        return None
    with open(p) as f:
        b = json.load(f)
    _bundle_cache[qid] = b
    return b


def _name_of(row):
    for k in _NAME_KEYS:
        if row.get(k):
            return str(row[k])
    return ""


def _match(bundle, category, item_name):
    rows = bundle.get("supplementals", {}).get(category, [])
    needle = str(item_name).strip().lower()
    return [r for r in rows if needle in _name_of(r).lower()]


# ── tool implementations ─────────────────────────────────────────────────────
def access_all(question_id):
    b = _load_bundle(question_id)
    if b is None:
        return {"error": f"unknown question_id '{question_id}'",
                "available": [p.stem for p in BUNDLE_DIR.glob('*.json')][:20]}
    _accessed.add(str(question_id))
    items = []
    for group, rows in b.get("supplementals", {}).items():
        for r in rows:
            items.append({"category": group, **{k: r[k] for k in _KEEP_NO_VALUE if k in r}})
    return {"question_id": question_id, "time_zero": b.get("time_zero"),
            "n_items": len(items), "items": items}


def request_a(question_id, category, item_name):
    if str(question_id) not in _accessed:
        return {"error": "gate not satisfied: call Access_All_supplementals_no_values first"}
    b = _load_bundle(question_id)
    if b is None:
        return {"error": f"unknown question_id '{question_id}'"}
    m = _match(b, category, item_name)
    return {"question_id": question_id, "category": category, "item_name": item_name,
            "n_matches": len(m), "matches": m}


def request_values(question_id, items):
    if str(question_id) not in _accessed:
        return {"error": "gate not satisfied: call Access_All_supplementals_no_values first"}
    b = _load_bundle(question_id)
    if b is None:
        return {"error": f"unknown question_id '{question_id}'"}
    results = []
    for it in (items or []):
        cat, name = it.get("category", ""), it.get("item_name", "")
        results.append({"category": cat, "item_name": name, "matches": _match(b, cat, name)})
    return {"question_id": question_id, "n_requested": len(results), "results": results}


TOOLS = [
    {"name": "Access_All_supplementals_no_values",
     "description": "List available supplemental items for a question (group+name+date, NO values). Gate; call first.",
     "inputSchema": {"type": "object", "properties": {"question_id": {"type": "string"}},
                     "required": ["question_id"]},
     "fn": lambda a: access_all(a["question_id"])},
    {"name": "Request_a_supplemental",
     "description": "Return the full value series for ONE named item.",
     "inputSchema": {"type": "object", "properties": {
         "question_id": {"type": "string"}, "category": {"type": "string"}, "item_name": {"type": "string"}},
         "required": ["question_id", "category", "item_name"]},
     "fn": lambda a: request_a(a["question_id"], a["category"], a["item_name"])},
    {"name": "Request_values",
     "description": "Batch-fetch ONLY the listed items in one call. items=[{category,item_name},...].",
     "inputSchema": {"type": "object", "properties": {
         "question_id": {"type": "string"},
         "items": {"type": "array", "items": {"type": "object", "properties": {
             "category": {"type": "string"}, "item_name": {"type": "string"}}}}},
         "required": ["question_id", "items"]},
     "fn": lambda a: request_values(a["question_id"], a.get("items", []))},
]
_BY_NAME = {t["name"]: t for t in TOOLS}


# ── minimal MCP JSON-RPC over stdio ──────────────────────────────────────────
def _send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _tools_list_payload():
    return [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params", {})
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "supplementals", "version": "0.1"}}})
        elif method == "notifications/initialized":
            continue                      # notification: no response
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": _tools_list_payload()}})
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {}) or {}
            tool = _BY_NAME.get(name)
            if tool is None:
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}})
                continue
            try:
                out = tool["fn"](args)
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(out)}], "isError": False}})
            except Exception as e:  # noqa: BLE001
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}})
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method {method}"}})


if __name__ == "__main__":
    main()
