"""
MCP tools for querying patient lab data from EHRSHOT.

Tool 1: request_all_labs_no_values  — shows lab names + dates, no values.
Tool 2: request_a_lab               — returns full result for one lab;
                                      gated: Tool 1 must be called first.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# EHRSHOT database path
# ---------------------------------------------------------------------------
_DEFAULT_EHRSHOT = (
    Path(__file__).parent.parent.parent
    / "EHRSHOT Hackathon Project"
    / "meds_reader_omop_ehrshot"
)
EHRSHOT_DB_PATH = Path(os.environ.get("EHRSHOT_DB_PATH", str(_DEFAULT_EHRSHOT)))

# ---------------------------------------------------------------------------
# LOINC → lab name mapping
# ---------------------------------------------------------------------------
LOINC_TO_LABEL: dict[str, str] = {
    "LOINC/2160-0":  "Creatinine",
    "LOINC/3094-0":  "BUN",
    "LOINC/2823-3":  "Potassium",
    "LOINC/2951-2":  "Sodium",
    "LOINC/1963-8":  "Bicarbonate",
    "LOINC/718-7":   "Hemoglobin",
    "LOINC/2345-7":  "Glucose",
    "LOINC/6690-2":  "WBC",
    "LOINC/777-3":   "Platelets",
    "LOINC/6301-6":  "INR",
    "LOINC/17861-6": "Calcium",
    "LOINC/2777-1":  "Phosphorus",
    "LOINC/1751-7":  "Albumin",
    "LOINC/2601-3":  "Magnesium",
    "LOINC/1742-6":  "ALT",
    "LOINC/2519-7":  "Lactate",
    "LOINC/10839-9": "Troponin I",
    "LOINC/42637-9": "BNP",
    "LOINC/62238-1": "eGFR",
    "LOINC/20570-8": "Hematocrit",
    "LOINC/2075-0":  "Chloride",
    "LOINC/33037-3": "Anion Gap",
    "LOINC/2085-9":  "HDL",
    "LOINC/2089-1":  "LDL",
    "LOINC/2093-3":  "Cholesterol",
    "LOINC/4548-4":  "HbA1c",
}

# Human reference ranges (low, high, unit) — used for flag computation
HUMAN_REF: dict[str, tuple] = {
    "Creatinine":  (0.5,  1.2,   "mg/dL"),
    "BUN":         (7.0,  25.0,  "mg/dL"),
    "Potassium":   (3.5,  5.0,   "mEq/L"),
    "Sodium":      (136,  145,   "mEq/L"),
    "Bicarbonate": (22,   29,    "mEq/L"),
    "Hemoglobin":  (12.0, 17.5,  "g/dL"),
    "Glucose":     (70,   99,    "mg/dL"),
    "WBC":         (4.5,  11.0,  "K/uL"),
    "Platelets":   (150,  400,   "K/uL"),
    "INR":         (0.9,  1.1,   "ratio"),
    "Calcium":     (8.5,  10.5,  "mg/dL"),
    "Phosphorus":  (2.5,  4.5,   "mg/dL"),
    "Albumin":     (3.5,  5.0,   "g/dL"),
    "Magnesium":   (1.7,  2.2,   "mg/dL"),
    "ALT":         (7,    56,    "U/L"),
    "Lactate":     (0.5,  2.0,   "mmol/L"),
    "Troponin I":  (0,    0.04,  "ng/mL"),
    "Hematocrit":  (36,   52,    "%"),
    "Chloride":    (98,   107,   "mEq/L"),
    "eGFR":        (60,   120,   "mL/min/1.73m2"),
    "Anion Gap":   (8,    16,    "mEq/L"),
    "HDL":         (40,   60,    "mg/dL"),
    "LDL":         (0,    100,   "mg/dL"),
    "Cholesterol": (0,    200,   "mg/dL"),
    "HbA1c":       (4.0,  5.6,   "%"),
    "BNP":         (0,    100,   "pg/mL"),
}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_labs_viewed: set[str] = set()           # subject_ids that called Tool 1
_patient_cache: dict[str, list[dict]] = {}  # per-subject lab rows
_db = None                                   # lazy-loaded SubjectDatabase


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_db():
    global _db
    if _db is None:
        import meds_reader
        _db = meds_reader.SubjectDatabase(str(EHRSHOT_DB_PATH))
    return _db


def _load_patient_labs(subject_id: str) -> list[dict]:
    if subject_id in _patient_cache:
        return _patient_cache[subject_id]

    db = _get_db()
    patient = db[int(subject_id)]

    rows: list[dict] = []
    seen: set = set()
    for event in patient.events:
        if event.table != "measurement":
            continue
        if event.code not in LOINC_TO_LABEL:
            continue
        if event.numeric_value is None:
            continue
        label = LOINC_TO_LABEL[event.code]
        date_str = event.time.strftime("%Y-%m-%d")
        key = (label, date_str)
        if key in seen:
            continue
        seen.add(key)

        ref = HUMAN_REF.get(label, (None, None, ""))
        rows.append({
            "label":     label,
            "date":      date_str,
            "value":     str(round(event.numeric_value, 2)),
            "unit":      event.unit or ref[2],
            "ref_lower": str(ref[0]) if ref[0] is not None else "",
            "ref_upper": str(ref[1]) if ref[1] is not None else "",
            "flag":      _flag(label, event.numeric_value),
        })

    rows.sort(key=lambda r: (r["date"], r["label"]))
    _patient_cache[subject_id] = rows
    return rows


def _flag(label: str, value: float) -> str:
    ref = HUMAN_REF.get(label)
    if ref is None:
        return ""
    lo, hi, _ = ref
    if value < lo:
        return "low"
    if value > hi:
        return "abnormal"
    return ""


def _to_markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep    = "| " + " | ".join("---" for _ in columns) + " |"
    lines  = [header, sep]
    for row in rows:
        cells = [str(row.get(c, "")) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 1 — request_all_labs_no_values
# ---------------------------------------------------------------------------

TOOL_ALL_LABS_NAME = "request_all_labs_no_values"

TOOL_ALL_LABS_SCHEMA = {
    "name": TOOL_ALL_LABS_NAME,
    "description": (
        "Returns a table of all lab tests on file for a patient, showing only "
        "the lab name and date taken — no result values. "
        "Call this first to orient yourself before requesting specific lab values."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "subject_id": {
                "type": "string",
                "description": "Patient subject_id (EHRSHOT integer ID).",
            },
        },
        "required": ["subject_id"],
    },
}


def execute_all_labs(arguments: dict) -> str:
    subject_id = str(arguments["subject_id"])
    rows = _load_patient_labs(subject_id)

    if not rows:
        return f"No lab records found for subject_id {subject_id}."

    table_rows = [{"Lab Name": r["label"], "Date Taken": r["date"]} for r in rows]
    table = _to_markdown_table(table_rows, ["Lab Name", "Date Taken"])

    _labs_viewed.add(subject_id)

    directive = (
        "\n\n> **IMPORTANT — Request ALL lab combinations "
        "(every lab name × date pair above) that are relevant to answering "
        "the clinical question. Exhaust every relevant combination before "
        "drawing conclusions.**"
    )
    return f"Labs for patient {subject_id}:\n\n{table}{directive}"


# ---------------------------------------------------------------------------
# Tool 2 — request_a_lab
# ---------------------------------------------------------------------------

TOOL_REQUEST_LAB_NAME = "request_a_lab"

TOOL_REQUEST_LAB_SCHEMA = {
    "name": TOOL_REQUEST_LAB_NAME,
    "description": (
        "Returns the full result for a single lab test (value, units, reference "
        "range, flag). Requires request_all_labs_no_values to have been called "
        "first for this patient. Input must include lab_name, date_taken, and "
        "a clinical justification."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "subject_id": {
                "type": "string",
                "description": "Patient subject_id (EHRSHOT integer ID).",
            },
            "request": {
                "type": "object",
                "description": (
                    "JSON object with fields: lab_name (string), "
                    "date_taken (string, YYYY-MM-DD), "
                    "justification (string)."
                ),
                "properties": {
                    "lab_name":     {"type": "string"},
                    "date_taken":   {"type": "string"},
                    "justification":{"type": "string"},
                },
                "required": ["lab_name", "date_taken", "justification"],
            },
        },
        "required": ["subject_id", "request"],
    },
}


def execute_request_lab(arguments: dict) -> str:
    subject_id = str(arguments["subject_id"])

    if subject_id not in _labs_viewed:
        return (
            "Access denied: you must call request_all_labs_no_values for "
            f"subject_id {subject_id} before requesting specific lab values."
        )

    req          = arguments.get("request", {})
    lab_name     = str(req.get("lab_name", "")).strip()
    date_taken   = str(req.get("date_taken", "")).strip()
    justification = str(req.get("justification", "")).strip()

    if not lab_name or not date_taken or not justification:
        return "Invalid request: lab_name, date_taken, and justification are all required."

    rows = _load_patient_labs(subject_id)
    matches = [
        r for r in rows
        if r["label"].lower() == lab_name.lower() and r["date"] == date_taken
    ]

    if not matches:
        return (
            f"No result found for lab '{lab_name}' on {date_taken} "
            f"for patient {subject_id}. "
            "Check the lab name and date against request_all_labs_no_values output."
        )

    columns_out = ["Lab Name", "Date Taken", "Value", "Unit",
                   "Ref Range Lower", "Ref Range Upper", "Flag"]
    out_rows = [{
        "Lab Name":        r["label"],
        "Date Taken":      r["date"],
        "Value":           r["value"],
        "Unit":            r["unit"],
        "Ref Range Lower": r["ref_lower"],
        "Ref Range Upper": r["ref_upper"],
        "Flag":            r["flag"],
    } for r in matches]

    table = _to_markdown_table(out_rows, columns_out)
    return (
        f"Lab result for '{lab_name}' on {date_taken} "
        f"(justification: {justification}):\n\n{table}"
    )
