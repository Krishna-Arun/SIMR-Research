#!/usr/bin/env python3
"""
Benchmark A — Supplementals MCP Server (stdio)

Serves each question's pre-time-zero supplemental data to the ANSWERING agent,
gated so values cannot be pulled until their existence has been acknowledged:

  * Access_All_supplementals_no_values(question_id) — list the supplemental items
    that exist for a question (category + item_name + date, NO values). Must be
    called before any value can be requested for that question.
  * Request_a_supplemental(question_id, category, item_name) — return the actual
    value(s) for one named item. Gated behind the access call.

Data source: one JSON "bundle" per question, produced by
`context_builder.to_supplemental_bundle()`, living in the directory given by
$SUPPLEMENTALS_DIR (default: ./supplementals/ next to this file). Each bundle is
`<question_id>.json` and contains ONLY pre-t0 pools — never the outcome/answer.

Run:  SUPPLEMENTALS_DIR=/path/to/bundles python server.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("supplementals")

BUNDLE_DIR = Path(os.environ.get(
    "SUPPLEMENTALS_DIR", Path(__file__).resolve().parent / "supplementals"))

# In-memory gate: question_ids for which Access_All_supplementals_no_values has
# been called this session. Mirrors the Version_1 kidney server's _labs_viewed.
_accessed: set[str] = set()
_bundle_cache: dict[str, dict] = {}


def _load_bundle(question_id: str) -> dict | None:
    if question_id in _bundle_cache:
        return _bundle_cache[question_id]
    path = BUNDLE_DIR / f"{question_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        b = json.load(f)
    _bundle_cache[question_id] = b
    return b


def _strip_values(item: dict) -> dict:
    """Keep only name/date-like fields; drop anything value-bearing."""
    keep = ("item_name", "test_name", "drug", "title", "charttime", "starttime",
            "chartdate", "category", "source", "direction", "spec_type", "icd_code")
    return {k: v for k, v in item.items() if k in keep}


@mcp.tool()
def Access_All_supplementals_no_values(question_id: str) -> dict:
    """List the supplemental items available for a question WITHOUT their values.

    Must be called before Request_a_supplemental for the same question_id.

    Args:
        question_id: the benchmark question identifier.

    Returns:
        {question_id, time_zero, items: [{category, ...name/date fields...}]} — no values.
    """
    b = _load_bundle(question_id)
    if b is None:
        return {"error": f"unknown question_id '{question_id}'",
                "available": [p.stem for p in BUNDLE_DIR.glob('*.json')][:20]}
    _accessed.add(str(question_id))
    items = []
    for category, rows in b.get("supplementals", {}).items():
        for r in rows:
            items.append({"category": category, **_strip_values(r)})
    return {"question_id": question_id, "time_zero": b.get("time_zero"),
            "n_items": len(items), "items": items}


@mcp.tool()
def Request_a_supplemental(question_id: str, category: str, item_name: str) -> dict:
    """Return the value(s) for one named supplemental item (with justification upstream).

    Gated behind Access_All_supplementals_no_values for the same question_id.

    Args:
        question_id: the benchmark question identifier.
        category: one of the supplemental categories (labs, microbiology, medications,
                  vitals_exam, dx_history, prior_procedures, fluids_output).
        item_name: the item's name as shown by the access call (matched loosely).

    Returns:
        {question_id, category, item_name, matches: [full value rows]}.
    """
    if str(question_id) not in _accessed:
        return {"error": "gate not satisfied: call Access_All_supplementals_no_values "
                         f"for question_id '{question_id}' first"}
    b = _load_bundle(question_id)
    if b is None:
        return {"error": f"unknown question_id '{question_id}'"}
    rows = b.get("supplementals", {}).get(category, [])
    needle = str(item_name).strip().lower()
    matches = [r for r in rows
               if needle in str(r.get("item_name") or r.get("test_name")
                                or r.get("drug") or r.get("title") or "").lower()]
    return {"question_id": question_id, "category": category, "item_name": item_name,
            "n_matches": len(matches), "matches": matches}


if __name__ == "__main__":
    mcp.run()
