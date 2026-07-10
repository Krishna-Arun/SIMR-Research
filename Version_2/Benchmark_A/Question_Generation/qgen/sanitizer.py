"""PHI gate for outbound PubMed calls.

The DUA-safe contract: only DE-IDENTIFIED clinical concepts (lab names, organism/antibiotic names,
disease/guideline terms) may leave the node toward PubMed — never patient identifiers, MIMIC-shifted
dates, or raw chart values. This module is the single chokepoint every tool argument passes through
before reaching the MCP server.

It is deliberately conservative: on any suspected leak it raises SanitizerError, and the agentic
loop turns that into a tool-error observation instructing the model to query with general clinical
concepts only.
"""
from __future__ import annotations

import re

# 7+ consecutive digits → looks like subject_id/hadm_id/specimen_id
_LONG_DIGITS = re.compile(r"\d{7,}")
# ISO-ish date or MIMIC-shifted datetime
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# value+unit pairs that read as raw chart measurements (e.g. "4.2 mmol/L", "13.5 mg/dL")
_VALUE_UNIT = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mmol/?l|mg/?dl|meq/?l|g/?dl|/ul|k/ul|mmhg|mcg|ng/?ml|u/?l)\b", re.I)

# string fields per tool that are allowed to carry free text (clinical concepts only)
_TEXT_FIELDS = {"query", "term", "field", "journal", "author", "affiliation"}


class SanitizerError(ValueError):
    pass


def sanitize_args(tool_name: str, args: dict, forbidden_ids: list[str] | None = None) -> dict:
    """Validate tool args; return them unchanged if clean, else raise SanitizerError."""
    forbidden = {str(x) for x in (forbidden_ids or []) if str(x)}
    for key, val in (args or {}).items():
        if isinstance(val, str):
            _check_str(key, val, forbidden)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    _check_str(key, item, forbidden)
    return args


def _check_str(key: str, s: str, forbidden: set[str]) -> None:
    # explicit patient identifiers are never allowed anywhere
    for fid in forbidden:
        if fid and fid in s:
            raise SanitizerError(f"patient identifier {fid!r} present in arg {key!r}")
    # pmid-bearing fields legitimately contain digits (article IDs returned by search) — allow them
    if key.lower() in {"pmid", "pmids", "id", "ids", "pmcid", "doi"}:
        return
    if _DATE.search(s):
        raise SanitizerError(f"date-like token in arg {key!r}: {s!r}")
    if _VALUE_UNIT.search(s):
        raise SanitizerError(f"raw chart value+unit in arg {key!r}: {s!r}")
    if _LONG_DIGITS.search(s):
        raise SanitizerError(f"long digit sequence (possible identifier) in arg {key!r}: {s!r}")


if __name__ == "__main__":  # quick self-test
    ok = sanitize_args("search_articles", {"query": "vancomycin MRSA bacteremia guideline"})
    print("clean OK:", ok)
    for bad in [{"query": "patient 10000032 sepsis"}, {"query": "lactate 4.2 mmol/L sepsis"},
                {"query": "admission 2150-04-12 workup"}]:
        try:
            sanitize_args("search_articles", bad, forbidden_ids=["10000032"])
            print("FAIL (should have raised):", bad)
        except SanitizerError as e:
            print("blocked:", e)
