#!/usr/bin/env python3
"""
Benchmark A - supplemental tool LOGIC (pure Python, no mcp dependency).

These functions are the single source of truth for the three local tools. They
are imported directly by the local gpt-oss harnesses (Python 3.9) AND wrapped by
mcp_server.py (FastMCP, Python 3.12) so the same behavior is exposed both ways.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.environ.get("BENCHA_INDEX", os.path.join(HERE, "index", "cases_index.json"))

_INDEX = None
_BY_HADM = None

def _load():
    global _INDEX, _BY_HADM
    if _INDEX is None:
        with open(INDEX_PATH) as f:
            _INDEX = json.load(f)
        _BY_HADM = {(str(e["subject_id"]), str(e["hadm_id"])): e for e in _INDEX.values()}
    return _INDEX, _BY_HADM


def _parse_cid(case_id):
    """case_id may carry a window tag: 'base|24h' (first-24h, diagnosis) or
    'base|pre' (full pre-treatment, treatment). Default = pre-treatment."""
    if "|" in case_id:
        base, tag = case_id.rsplit("|", 1)
        return base, ("first24h" if tag == "24h" else "pretreatment")
    return case_id, "pretreatment"


def _sliced(entry, window):
    """Return supplementals filtered to the window end (timestamps are
    'YYYY-MM-DD HH:MM:SS' strings -> lexical compare == chronological)."""
    end = entry["first24h_end"] if window == "first24h" else entry["pretreatment_end"]
    end_date = end[:10]
    sup = entry["supplementals"]
    return {
        "labs": {lab: [r for r in rows if r["t"] < end]
                 for lab, rows in sup["labs"].items()
                 if any(r["t"] < end for r in rows)},
        "medications": [m for m in sup["medications"] if m["starttime"] < end],
        "coronary_contrast": [c for c in sup["coronary_contrast"] if c["chartdate"] <= end_date],
        "demographics": sup["demographics"],
        "comorbidities": sup["comorbidities"],
    }


def _catalog(sup):
    return {
        "labs": [{"name": lab, "n": len(rows), "timestamps": [r["t"] for r in rows]}
                 for lab, rows in sorted(sup["labs"].items())],
        "medications": [{"name": m["drug"], "starttime": m["starttime"], "route": m["route"]}
                        for m in sup["medications"]],
        "coronary_contrast": [{"name": c["title"] or c["icd"], "date": c["chartdate"]}
                              for c in sup["coronary_contrast"]],
        "demographics": {"available_fields": list(sup["demographics"].keys())},
        "comorbidities": {"available": True,
                          "note": "request name 'comorbidities' for the flag profile"},
        "_usage": "Call request_a_supplemental(case_id, name, causal_justification) for values. "
                  "Use a lab's exact name, or one of: 'medications', 'coronary_contrast', "
                  "'demographics', 'comorbidities'.",
    }


def request_all_supplementals_no_values(case_id: str) -> dict:
    index, _ = _load()
    base, window = _parse_cid(case_id)
    e = index.get(base)
    if e is None:
        return {"error": f"unknown case_id {case_id!r}"}
    end = e["first24h_end"] if window == "first24h" else e["pretreatment_end"]
    return {"case_id": case_id, "window": {"start": e["admit"], "end": end},
            "catalog": _catalog(_sliced(e, window))}


def request_a_supplemental(case_id: str, name: str, causal_justification: str) -> dict:
    index, _ = _load()
    base, window = _parse_cid(case_id)
    e = index.get(base)
    if e is None:
        return {"error": f"unknown case_id {case_id!r}"}
    if not causal_justification or not causal_justification.strip():
        return {"error": "causal_justification is required"}
    sup = _sliced(e, window)
    key = name.strip().lower()
    if key in ("medications", "meds", "medication"):
        payload = {"type": "medications", "data": sup["medications"]}
    elif key in ("coronary_contrast", "contrast", "coronary", "cath"):
        payload = {"type": "coronary_contrast", "data": sup["coronary_contrast"]}
    elif key in ("demographics", "demographic"):
        payload = {"type": "demographics", "data": sup["demographics"]}
    elif key in ("comorbidities", "comorbidity"):
        payload = {"type": "comorbidities", "data": sup["comorbidities"]}
    else:
        match = next((lab for lab in sup["labs"] if lab.lower() == key), None)
        if match is None:
            return {"error": f"no supplemental named {name!r}",
                    "available_labs": sorted(sup["labs"].keys())}
        payload = {"type": "lab", "name": match, "data": sup["labs"][match]}
    return {"case_id": case_id, "requested": name,
            "causal_justification": causal_justification, **payload}


def get_patient_data(subject_id: str, hadm_id: str, window: str = "pretreatment") -> dict:
    """GENERATION-ONLY: full record incl. ground truth, supplementals sliced to
    `window` ('first24h' for diagnosis, 'pretreatment' for treatment)."""
    _, by_hadm = _load()
    e = by_hadm.get((str(subject_id), str(hadm_id)))
    if e is None:
        return {"error": f"no indexed case for subject {subject_id} / hadm {hadm_id}"}
    return {**{k: v for k, v in e.items() if k != "supplementals"},
            "window": window, "supplementals": _sliced(e, window)}
