"""Optimizer agent (Mixtral) — drafts and refines a question + answer key for one patient.

Runs inside the agentic loop so it can consult PubMed to justify which labs/micro matter (gold set)
and to attach guideline citations. Output is a CANDIDATE dict (see schema.CANDIDATE_TEMPLATE).
"""
from __future__ import annotations

import json

from qgen.agentic_loop import run_agentic
from qgen.schema import CANDIDATE_TEMPLATE


def render_context(context: dict) -> str:
    """Compact, leakage-free view of the patient for the prompt (names + summary, not full series)."""
    demo = context.get("demographics", {})
    labs = context.get("labs_summary", {})
    lab_lines = []
    for name, s in sorted(labs.items()):
        flag = " *ABNORMAL" if s.get("any_abnormal") else ""
        lab_lines.append(f"  - {name}: latest {s.get('latest')} {s.get('unit','')} "
                         f"(range {s.get('min')}–{s.get('max')}, n={s.get('n')}){flag}")
    micro_lines = []
    for m in context.get("microbiology", []):
        org = m.get("organism") or "no growth"
        ab = f", {m['antibiotic']}={m['interpretation']}" if m.get("antibiotic") else ""
        micro_lines.append(f"  - {m.get('specimen','')}/{m.get('test','')}: {org}{ab}")
    return (
        f"PATIENT (pre-time-zero only; time-zero={context.get('time_zero_policy')}):\n"
        f"  age {demo.get('anchor_age','?')} {demo.get('gender','?')}, "
        f"admission_type {demo.get('admission_type','?')}\n"
        f"  comorbidities: {', '.join(context.get('comorbidities', {})) or 'none coded'}\n"
        f"AVAILABLE LABS (only these may be the answer's evidence):\n" + ("\n".join(lab_lines) or "  (none)") +
        f"\nMICROBIOLOGY:\n" + ("\n".join(micro_lines) or "  (none)")
    )


DRAFT_INSTRUCTIONS = """You write ONE high-quality clinical {qtype} question about THIS specific CARDIOVASCULAR
patient for a benchmark that tests whether an AI can REQUEST the right labs/microbiology (with
patient-specific justification) and then ANSWER with a causal explanation.

CARDIAC FOCUS (required) — the question must be about cardiovascular medicine:
- This patient's primary problem is cardiovascular. The question MUST concern a CARDIOVASCULAR diagnosis
  or a cardiac-relevant management decision (e.g. myocardial ischemia/infarction, heart failure, valve
  disease, arrhythmia, cardiorenal syndrome, cardiogenic shock).
- Build gold_labs from CARDIAC-RELEVANT labs when present (e.g. Troponin, CK-MB, NT-proBNP/BNP, Lactate,
  Creatinine/Urea for cardiorenal, Potassium/Magnesium for arrhythmia, Bicarbonate/anion gap for perfusion).
- Do NOT build the question around an incidental NON-cardiac finding (e.g. an isolated elevated amylase →
  pancreatitis). If the only abnormal labs are non-cardiac, prefer a different framing or expect rejection.

DO NOT LEAK THE LABS IN THE STEM (critical) — the test-taker must REQUEST the labs themselves:
- question_text must NOT name any lab, must NOT state any lab value, and must NOT say which labs are
  abnormal. Describe only the clinical situation/decision: who the patient is, the cardiovascular context,
  and what must be determined.
- question_text must also NOT name the diagnosis/answer or pile up buzzwords (no "STEMI", "septic shock",
  "AKI", "start dialysis", etc.). All lab names/values, the diagnosis, and buzzwords belong ONLY in
  gold_labs / reference_answer / causal_chain — NEVER in question_text.
- GOOD stem (SCHEMATIC — you MUST instantiate it with THIS patient's real age/sex/presentation from the
  PATIENT block above; do NOT copy this sentence literally): "A <age>-year-old <sex> admitted for <reason>
  has <acute change overnight>; determine the most likely cardiac cause of the change."
  BAD stem: "...with elevated troponin and a rising creatinine, what is..."

Requirements:
- Answerable ONLY using this patient's LABS and MICROBIOLOGY above — not vitals, imaging, or notes.
- gold_labs/gold_micro drawn ONLY from labs/micro actually present above; each clinically necessary for THIS
  patient; use PubMed to cite a guideline supporting each.
- reference_answer + a causal_chain with >=2 linked steps (finding -> mechanism -> ...).
- type must be "{qtype}".

BREVITY (critical — keep the JSON COMPLETE, never truncated): include only the 3-5 MOST decision-relevant
gold_labs; keep each proposed_reason and each guideline_citation.claim to ONE short sentence; causal_chain
= 2-4 short steps. Completeness beats verbosity — EVERY field (question_text, reference_answer, the full
causal_chain, and gold_labs each with a citation) MUST be fully present and not cut off.

FINAL SELF-CHECK before you output (a stem that names the answer is AUTO-REJECTED): re-read question_text.
It must NOT contain reference_answer, ANY diagnosis/syndrome name (e.g. "cardiogenic shock", "STEMI",
"sepsis", "AKI"), ANY lab name, or ANY lab value. If it does, REWRITE question_text to describe ONLY the
presentation and the decision to make (who the patient is, what changed, what must be determined) and keep
every diagnosis term in reference_answer and every lab in gold_labs. Example —
  BAD : "Manage this patient's cardiogenic shock given the rising lactate."
  GOOD (SCHEMATIC — fill with THIS patient's real age/sex/presentation; NEVER copy the example verbatim):
       "A <age>-year-old <sex> admitted for <reason> developed <acute change>; determine the most likely
        cardiac cause and the appropriate next management step."

USE THIS PATIENT (critical): question_text MUST use the ACTUAL age and sex shown in the PATIENT block above
— never a placeholder and never the number from any example. Two different patients must NEVER receive the
same stem; the stem has to read as if written for this specific patient's age, sex, and admission reason.

Return your final answer as {{"action":"final","result":<CANDIDATE>}} where CANDIDATE matches:
{template}"""


class OptimizerAgent:
    def __init__(self, llm, dispatcher, mcp_tools, budget: int):
        self.llm = llm
        self.dispatcher = dispatcher
        self.mcp_tools = mcp_tools
        self.budget = budget

    def _run(self, context, messages) -> dict | None:
        forbidden = [str(context["subject_id"]), str(context["hadm_id"])]
        return run_agentic(self.llm, self.dispatcher, self.mcp_tools, messages,
                           budget=self.budget, forbidden_ids=forbidden)

    def draft(self, context: dict, qtype: str) -> dict | None:
        prompt = (render_context(context) + "\n\n" +
                  DRAFT_INSTRUCTIONS.format(qtype=qtype,
                                            template=json.dumps(CANDIDATE_TEMPLATE, indent=2)))
        return self._run(context, [{"role": "user", "content": prompt}])

    def refine(self, context: dict, qtype: str, prev: dict, feedback: str) -> dict | None:
        prompt = (render_context(context) + "\n\n" +
                  DRAFT_INSTRUCTIONS.format(qtype=qtype,
                                            template=json.dumps(CANDIDATE_TEMPLATE, indent=2)) +
                  f"\n\nYOUR PREVIOUS DRAFT:\n{json.dumps(prev, default=str)[:8000]}"
                  f"\n\nEVALUATOR FEEDBACK (address ALL of it):\n{feedback}")
        return self._run(context, [{"role": "user", "content": prompt}])
