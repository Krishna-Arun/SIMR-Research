"""
MCP tools for querying patient lab data from MIMIC-IV.

Tool 1: request_all_labs_no_values  — shows lab names + dates, no values.
Tool 2: request_a_lab               — returns full data for one lab entry;
                                      gated: requires Tool 1 to have been
                                      called first for the same subject_id.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Data path
# ---------------------------------------------------------------------------
_DEFAULT_MIMIC_HOSP = (
    Path(__file__).parent.parent.parent
    / "mimic-iv-clinical-database-demo-2.2"
    / "hosp"
)
MIMIC_HOSP = Path(os.environ.get("MIMIC_DATA_DIR", str(_DEFAULT_MIMIC_HOSP)))

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_labs_viewed: set[str] = set()          # subject_ids that have called Tool 1
_patient_lab_cache: dict[str, pd.DataFrame] = {}  # per-subject merged df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_patient_labs(subject_id: str) -> pd.DataFrame:
    if subject_id not in _patient_lab_cache:
        labevents = pd.read_csv(MIMIC_HOSP / "labevents.csv.gz", low_memory=False)
        d_labitems = pd.read_csv(MIMIC_HOSP / "d_labitems.csv.gz")
        merged = labevents.merge(d_labitems[["itemid", "label"]], on="itemid")
        _patient_lab_cache[subject_id] = merged[
            merged["subject_id"] == int(subject_id)
        ].copy()
    return _patient_lab_cache[subject_id]


def _to_markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in rows:
        cells = [str(row.get(c, "")) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_date(charttime: Any) -> str:
    """Return just the date portion of a charttime string."""
    return str(charttime).split(" ")[0]


# ---------------------------------------------------------------------------
# Tool 1 — request_all_labs_no_values
# ---------------------------------------------------------------------------

TOOL_ALL_LABS_NAME = "request_all_labs_no_values"

TOOL_ALL_LABS_SCHEMA = {
    "name": TOOL_ALL_LABS_NAME,
    "description": (
        "Returns a table of all lab tests ordered for a patient, showing only "
        "the lab name and date taken — no result values are included. "
        "Call this first to orient yourself before requesting specific lab values."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "subject_id": {
                "type": "string",
                "description": "MIMIC-IV patient subject_id.",
            },
        },
        "required": ["subject_id"],
    },
}


def execute_all_labs(arguments: dict) -> str:
    subject_id = str(arguments["subject_id"])
    df = _get_patient_labs(subject_id)

    if df.empty:
        return f"No lab records found for subject_id {subject_id}."

    # Deduplicate and sort
    summary = (
        df[["label", "charttime"]]
        .drop_duplicates()
        .sort_values("charttime")
        .rename(columns={"label": "Lab Name", "charttime": "Date Taken"})
    )
    summary["Date Taken"] = summary["Date Taken"].apply(_format_date)
    summary = summary.drop_duplicates()

    rows = summary.to_dict(orient="records")
    table = _to_markdown_table(rows, ["Lab Name", "Date Taken"])

    # Mark this patient as oriented
    _labs_viewed.add(subject_id)

    directive = (
        "\n\n> **IMPORTANT — You must request ALL possible lab combinations "
        "(every lab name × date pair above) that are relevant to answering "
        "the clinical question. Do not stop after retrieving one or two labs — "
        "exhaust every combination that could contribute to the answer before "
        "drawing any conclusions.**"
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
                "description": "MIMIC-IV patient subject_id.",
            },
            "request": {
                "type": "object",
                "description": (
                    "JSON object with fields: lab_name (string), "
                    "date_taken (string, YYYY-MM-DD), "
                    "justification (string)."
                ),
                "properties": {
                    "lab_name": {"type": "string"},
                    "date_taken": {"type": "string"},
                    "justification": {"type": "string"},
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

    req = arguments.get("request", {})
    lab_name = str(req.get("lab_name", "")).strip()
    date_taken = str(req.get("date_taken", "")).strip()
    justification = str(req.get("justification", "")).strip()

    if not lab_name or not date_taken or not justification:
        return (
            "Invalid request: all three fields (lab_name, date_taken, "
            "justification) are required."
        )

    df = _get_patient_labs(subject_id)

    # Case-insensitive label match, date-only comparison
    mask = (
        df["label"].str.strip().str.lower() == lab_name.lower()
    ) & (
        df["charttime"].astype(str).str.startswith(date_taken)
    )
    matches = df[mask]

    if matches.empty:
        return (
            f"No result found for lab '{lab_name}' on {date_taken} "
            f"for patient {subject_id}. "
            "Check the lab name and date against request_all_labs_no_values output."
        )

    columns_out = ["Lab Name", "Date Taken", "Value", "Unit", "Ref Range Lower", "Ref Range Upper", "Flag"]
    rows = []
    for _, row in matches.iterrows():
        rows.append({
            "Lab Name": row["label"],
            "Date Taken": _format_date(row["charttime"]),
            "Value": row.get("value", ""),
            "Unit": row.get("valueuom", ""),
            "Ref Range Lower": row.get("ref_range_lower", ""),
            "Ref Range Upper": row.get("ref_range_upper", ""),
            "Flag": row.get("flag", ""),
        })

    table = _to_markdown_table(rows, columns_out)
    return (
        f"Lab result for '{lab_name}' on {date_taken} "
        f"(justification: {justification}):\n\n{table}"
    )
