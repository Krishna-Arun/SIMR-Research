#!/usr/bin/env python3
"""
Benchmark A - local MCP server (supplemental information provider).

Thin FastMCP wrapper over supplemental_tools.py (the shared, mcp-free logic).
Runs on Python 3.12 (.venv_mcp). Serves per-patient supplementals for the first
24h after admission.

Tools:
  request_all_supplementals_no_values(case_id)      -> catalog (names+times, NO values)
  request_a_supplemental(case_id, name, causal_justification) -> values for one item
  get_patient_data(subject_id, hadm_id)   [GENERATION-ONLY] -> full record + ground truth

Run:  .venv_mcp/bin/python mcp_server.py     (stdio transport)
"""
from mcp.server.fastmcp import FastMCP
import supplemental_tools as T

mcp = FastMCP("benchmark-a-supplementals")


@mcp.tool()
def request_all_supplementals_no_values(case_id: str) -> dict:
    """Catalog of available supplementals (names + timestamps only, NO values) for
    the patient's first 24h after admission."""
    return T.request_all_supplementals_no_values(case_id)


@mcp.tool()
def request_a_supplemental(case_id: str, name: str, causal_justification: str) -> dict:
    """All values of ONE supplemental (a lab name, or 'medications' / 'coronary_contrast'
    / 'demographics' / 'comorbidities') across the first-24h window. A patient-specific
    causal_justification is REQUIRED (recorded for scoring, not graded here)."""
    return T.request_a_supplemental(case_id, name, causal_justification)


@mcp.tool()
def get_patient_data(subject_id: str, hadm_id: str) -> dict:
    """[GENERATION-ONLY] Full record (all supplementals + ground truth) for one admission.
    Used by question generation / the discard-gate scorer. Do NOT expose to the answering agent."""
    return T.get_patient_data(subject_id, hadm_id)


if __name__ == "__main__":
    mcp.run()
