"""Finalize an accepted candidate into a full answer key.

- Attach each gold lab's ACTUAL patient values from the chart (latest value, unit, abnormal flag,
  hours-from-time-zero) so the key reflects ground truth, not the model's recollection.
- Re-validate every cited PMID via the PubMed MCP server (validate_pmid); drop unverifiable cites
  (anti-hallucination). Citations that survive are deduped.
"""
from __future__ import annotations

import json

from qgen.tools import ToolDispatcher


def _attach_patient_values(context: dict, gold_labs: list[dict]) -> list[dict]:
    summ = context.get("labs_summary", {})
    full = context.get("labs_full", {})
    out = []
    for g in gold_labs or []:
        label = str(g.get("label", ""))
        rec = dict(g)
        if label in summ:
            s = summ[label]
            rec["patient_value"] = s.get("latest")
            rec["unit"] = s.get("unit")
            rec["abnormal_flag"] = bool(s.get("any_abnormal"))
            rec["n_measurements"] = s.get("n")
            rec["in_chart"] = True
        else:
            rec["in_chart"] = False
        if label in full and full[label]:
            rec["last_charttime_offset_h"] = full[label][-1]["hours_from_index"]
        out.append(rec)
    return out


def _collect_pmids(candidate: dict) -> set[str]:
    pmids = set()
    for g in candidate.get("gold_labs", []) + candidate.get("gold_micro", []):
        cite = (g or {}).get("guideline_citation") or {}
        if cite.get("pmid"):
            pmids.add(str(cite["pmid"]))
    for c in candidate.get("pubmed_citations", []):
        if (c or {}).get("pmid"):
            pmids.add(str(c["pmid"]))
    return pmids


def _validate_pmids(dispatcher: ToolDispatcher, pmids: set[str]) -> set[str]:
    valid = set()
    for pmid in pmids:
        if not pmid.isdigit():
            continue
        try:
            res = dispatcher.dispatch("validate_pmid", {"pmid": pmid})
        except Exception:
            continue
        if res.startswith("TOOL_ERROR"):
            continue
        # the tool returns JSON; treat a truthy/valid signal as confirmation
        ok = False
        try:
            obj = json.loads(res)
            ok = bool(obj.get("valid", obj.get("exists", obj.get("isValid", True))))
        except json.JSONDecodeError:
            ok = "true" in res.lower() or "valid" in res.lower()
        if ok:
            valid.add(pmid)
    return valid


def build(context: dict, candidate: dict, dispatcher: ToolDispatcher) -> dict:
    """Return a finalized candidate with patient values attached and citations verified."""
    final = dict(candidate)
    final["gold_labs"] = _attach_patient_values(context, candidate.get("gold_labs", []))

    valid = _validate_pmids(dispatcher, _collect_pmids(candidate))

    def _filter_cite(g):
        cite = (g or {}).get("guideline_citation") or {}
        if cite.get("pmid") and str(cite["pmid"]) not in valid:
            g = dict(g)
            g["guideline_citation"] = {**cite, "verified": False}
        elif cite.get("pmid"):
            g["guideline_citation"] = {**cite, "verified": True}
        return g

    final["gold_labs"] = [_filter_cite(g) for g in final["gold_labs"]]
    final["gold_micro"] = [_filter_cite(g) for g in candidate.get("gold_micro", [])]
    final["pubmed_citations"] = [c for c in candidate.get("pubmed_citations", [])
                                 if str((c or {}).get("pmid", "")) in valid]
    final["n_verified_citations"] = len(valid)
    return final
