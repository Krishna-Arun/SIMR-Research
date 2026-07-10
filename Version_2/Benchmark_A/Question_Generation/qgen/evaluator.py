"""Evaluator agent (DeepSeek-R1) — critiques a candidate on 4 dims, max 3 iterations upstream.

Hybrid: hard-to-game AUTOMATIC checks (against the real chart) AND model judgment (incl. PubMed
guideline verification). A dimension passes only if BOTH the automatic check (where one exists) and
the model agree — the model can restrict but not loosen the automatic verdict.
"""
from __future__ import annotations

import json

from qgen.agentic_loop import run_agentic
from qgen.schema import EVAL_DIMS, VERDICT_TEMPLATE

_MECHANISM = ("->", "because", "due to", "leads to", "causes", "results in", "secondary to",
              "mechanism", "induces", "impairs", "elevat", "reduc", "increas", "decreas")
_NON_LAB_SOURCES = ("x-ray", "ct scan", "ct angiogram", "mri", "ultrasound", "echocardiogram",
                    "chest film", "radiograph", "imaging", "blood pressure", "heart rate",
                    "physical exam", "auscultation", "the note", "nursing note")


def _auto_checks(context: dict, candidate: dict) -> dict:
    labs_summary = context.get("labs_summary", {})
    chart_labels = set(labs_summary)
    gold = candidate.get("gold_labs", []) or []
    gold_labels = [str(g.get("label", "")) for g in gold]
    qtext = str(candidate.get("question_text", "")).lower()

    # 1. answerable only with labs/micro: gold set non-empty + all in chart + no non-lab data demanded
    #    + the stem must NOT leak any lab name (the test-taker must REQUEST the labs itself).
    in_chart = [lbl for lbl in gold_labels if lbl in chart_labels]
    no_other = not any(tok in qtext for tok in _NON_LAB_SOURCES)
    leak_labs = [lbl for lbl in chart_labels if lbl.lower() in qtext]
    d1 = bool(gold_labels) and len(in_chart) == len(gold_labels) and no_other and not leak_labs

    # 2. patient-specific: >=1 gold lab present AND abnormal in this chart
    abn = [lbl for lbl in in_chart if labs_summary.get(lbl, {}).get("any_abnormal")]
    d2 = len(abn) >= 1

    # 3. causal reasoning: chain has >=2 linked steps / mechanism markers
    chain = " -> ".join(str(x) for x in (candidate.get("causal_chain") or []))
    arrows = chain.count("->")
    mech = sum(1 for m in _MECHANISM if m in chain.lower())
    d3 = arrows >= 2 or (arrows >= 1 and mech >= 2)

    # 4. guideline-grounded precheck: >=1 pmid attached (model verifies for real)
    has_pmid = any(((g or {}).get("guideline_citation") or {}).get("pmid") for g in gold)
    d4 = bool(has_pmid)

    return {
        "answerable_with_labs_micro": {"pass": d1, "reason": f"{len(in_chart)}/{len(gold_labels)} gold labs in chart; no_other_source={no_other}; labs_leaked_in_stem={leak_labs}"},
        "patient_specific": {"pass": d2, "reason": f"{len(abn)} gold labs abnormal in chart"},
        "requires_causal_reasoning": {"pass": d3, "reason": f"{arrows} arrows, {mech} mechanism markers"},
        "guideline_grounded": {"pass": d4, "reason": f"pmid_attached={has_pmid}"},
    }


EVAL_INSTRUCTIONS = """You are a strict clinical benchmark reviewer. Judge the candidate question+answer
key for THIS patient on 4 dimensions, using PubMed to verify guideline support:
  1. answerable_with_labs_micro — answerable ONLY from this patient's labs/microbiology.
  2. patient_specific — grounded in THIS patient's actual abnormal findings, not a textbook question.
  3. requires_causal_reasoning — needs a >=2-step causal chain, not a single fact lookup.
  4. guideline_grounded — each gold lab's relevance is supported by a REAL PubMed citation (verify PMIDs).
For each gold lab give a verdict (keep / drop:<reason>) incl. whether a real guideline supports it.
Be specific and actionable so the writer can fix issues.

CRITICAL — NO BUZZWORD BINGO and NO LAB LEAKAGE: the question stem must NOT telegraph its own answer.
You MUST FAIL dimension 1 (answerable_with_labs_micro) if the stem:
  (a) names the diagnosis/syndrome/intervention that is the reference answer (e.g. "STEMI", "septic shock",
      "AKI", "give dialysis"), or piles up diagnostic buzzwords; OR
  (b) NAMES ANY LAB or states/implies any lab value or which labs are abnormal — the test-taker must
      REQUEST the labs itself, so a stem that hands them the labs is answerable by bingo, not by labs.
Say so in actionable_feedback (tell the writer to describe only the clinical situation, moving all lab
names/values and diagnosis terms into gold_labs/reference_answer only).

CARDIAC FOCUS: this is a cardiovascular patient. If the question is built around an INCIDENTAL non-cardiac
finding (e.g. an isolated amylase -> pancreatitis) rather than a cardiovascular diagnosis/decision, FAIL
patient_specific as off-target and tell the writer to refocus on the cardiac problem.

Return {{"action":"final","result":<VERDICT>}} where VERDICT matches:
{template}"""


class EvaluatorAgent:
    def __init__(self, llm, dispatcher, mcp_tools, budget: int):
        self.llm = llm
        self.dispatcher = dispatcher
        self.mcp_tools = mcp_tools
        self.budget = budget

    def evaluate(self, context: dict, candidate: dict) -> dict:
        auto = _auto_checks(context, candidate)
        forbidden = [str(context["subject_id"]), str(context["hadm_id"])]
        prompt = (f"CANDIDATE:\n{json.dumps(candidate, default=str)[:8000]}\n\n"
                  f"PATIENT ABNORMAL LABS: "
                  f"{[k for k,v in context.get('labs_summary',{}).items() if v.get('any_abnormal')][:40]}\n\n"
                  + EVAL_INSTRUCTIONS.format(template=json.dumps(VERDICT_TEMPLATE, indent=2)))
        model = run_agentic(self.llm, self.dispatcher, self.mcp_tools,
                            [{"role": "user", "content": prompt}],
                            budget=self.budget, forbidden_ids=forbidden) or {}
        return self._merge(auto, model)

    @staticmethod
    def _merge(auto: dict, model: dict) -> dict:
        model_dims = model.get("dims", {}) if isinstance(model, dict) else {}
        dims = {}
        for d in EVAL_DIMS:
            a = auto.get(d, {"pass": True, "reason": ""})
            m = model_dims.get(d, {})
            m_pass = bool(m.get("pass", True)) if isinstance(m, dict) else bool(m)
            # model can only restrict the automatic verdict
            final_pass = bool(a["pass"]) and m_pass
            reason = f"auto: {a.get('reason','')} | model: {m.get('reason','') if isinstance(m, dict) else ''}"
            dims[d] = {"pass": final_pass, "reason": reason, "auto": a["pass"], "model": m_pass}
        accept = all(dims[d]["pass"] for d in EVAL_DIMS)
        return {
            "dims": dims,
            "gold_lab_verdicts": model.get("gold_lab_verdicts", []) if isinstance(model, dict) else [],
            "accept": accept,
            "actionable_feedback": (model.get("actionable_feedback", "") if isinstance(model, dict) else "")
                                   or _auto_feedback(dims),
        }


def _auto_feedback(dims: dict) -> str:
    fails = [f"{d}: {dims[d]['reason']}" for d in dims if not dims[d]["pass"]]
    return "Fix: " + "; ".join(fails) if fails else "All dimensions pass."
