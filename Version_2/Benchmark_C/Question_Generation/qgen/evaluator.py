"""Benchmark C evaluator — critiques an intervention-identification candidate (hybrid auto+model),
enforces correctness (optimizer's predicted_owner == ground truth) and bans answer leakage in the stem.
"""
from __future__ import annotations

import json
import re

from qgen.agentic_loop import run_agentic
from qgen.schema import EVAL_DIMS, VERDICT_TEMPLATE

_MECHANISM = ("->", "because", "due to", "leads to", "causes", "results in", "clearance", "removes",
              "depletes", "shifts", "dilutes", "transfus", "ventilat", "dialy", "increas", "decreas", "reduc")
# Patterns that would reveal which patient owns the shown post-state (answer leakage in the stem).
_LEAK_RE = [re.compile(p, re.I) for p in (
    r"\bpatient\s+[ab]\b.{0,50}\b(had|underwent|received|got|produced|owns|is the (one|patient)|answer|correct)\b",
    r"\b(had|underwent|received|produced|owns|answer|correct)\b.{0,30}\bpatient\s+[ab]\b",
    r"\b(post-?procedure|post-?state|shown labs|observed labs)\b.{0,40}\bpatient\s+[ab]\b",
    r"\bpatient\s+[ab]\b.{0,40}\b(post-?procedure|post-?state|shown labs|observed labs)\b",
    r"belongs to patient", r"the post-?state belongs", r"ground truth", r"the answer is\b",
)]


def _auto_checks(context: dict, candidate: dict) -> dict:
    truth = context["shown_post_owner"]
    pred = str(candidate.get("predicted_owner", "")).upper().strip()
    just = str(candidate.get("causal_justification", ""))
    qtext = str(candidate.get("question_text", "")).lower()

    # 1. answerable_from_states: optimizer got the owner right + stem doesn't leak which patient
    leak = any(rx.search(qtext) for rx in _LEAK_RE)
    d1 = (pred == truth) and not leak

    # 2. patient_specific: justification cites concrete values
    d2 = any(ch.isdigit() for ch in just)

    # 3. requires_causal_reasoning: mechanism markers + contrasts both procedures
    n_mech = sum(m in just.lower() for m in _MECHANISM)
    feats = candidate.get("distinguishing_features", [])
    d3 = n_mech >= 1 and len(feats) >= 1

    # 4. guideline_grounded precheck: >=1 pmid
    has_pmid = any((c or {}).get("pmid") for c in candidate.get("pubmed_citations", []))
    d4 = has_pmid

    return {
        "answerable_from_states": {"pass": d1, "reason": f"pred={pred} truth={truth} leak={leak}"},
        "patient_specific": {"pass": d2, "reason": "justification cites values" if d2 else "no concrete values"},
        "requires_causal_reasoning": {"pass": d3, "reason": f"{n_mech} mechanism markers, {len(feats)} features"},
        "guideline_grounded": {"pass": d4, "reason": f"pmid_attached={has_pmid}"},
    }


EVAL_INSTRUCTIONS = """You review a counterfactual intervention-identification question on 4 dimensions,
verifying guideline support via PubMed:
  1. answerable_from_states — the shown post-state is genuinely distinguishable via the two procedures'
     causal effects (not a coin flip), and the stated answer patient is correct.
  2. patient_specific — the justification cites the patients' actual baseline/post values.
  3. requires_causal_reasoning — a >=2-step causal contrast of procedure X vs Y, not a guess.
  4. guideline_grounded — each procedure's physiologic effect is supported by a REAL PubMed citation.

CRITICAL — NO LEAKAGE / NO BUZZWORD BINGO: the question stem must NOT reveal which patient is the answer,
must not name the diagnosis, and must present A and B neutrally. If it leaks, FAIL answerable_from_states
and tell the writer to neutralize the stem.

Return {{"action":"final","result":<VERDICT>}} where VERDICT matches:
{template}"""


class EvaluatorAgent:
    def __init__(self, llm, dispatcher, mcp_tools, budget: int):
        self.llm, self.dispatcher, self.mcp_tools, self.budget = llm, dispatcher, mcp_tools, budget

    def evaluate(self, context: dict, candidate: dict) -> dict:
        auto = _auto_checks(context, candidate)
        forbidden = [str(context["patient_A"]["demographics"]["hadm_id"]),
                     str(context["patient_B"]["demographics"]["hadm_id"])]
        prompt = (f"CANDIDATE:\n{json.dumps(candidate, default=str)[:8000]}\n\n"
                  f"PROCEDURES: A={context['procA']} | B={context['procB']}\n"
                  + EVAL_INSTRUCTIONS.format(template=json.dumps(VERDICT_TEMPLATE, indent=2)))
        model = run_agentic(self.llm, self.dispatcher, self.mcp_tools,
                            [{"role": "user", "content": prompt}],
                            budget=self.budget, forbidden_ids=forbidden) or {}
        return self._merge(auto, model)

    @staticmethod
    def _merge(auto: dict, model: dict) -> dict:
        mdims = model.get("dims", {}) if isinstance(model, dict) else {}
        dims = {}
        for d in EVAL_DIMS:
            a = auto.get(d, {"pass": True, "reason": ""})
            m = mdims.get(d, {})
            final = bool(a["pass"]) and (bool(m.get("pass", True)) if isinstance(m, dict) else bool(m))
            dims[d] = {"pass": final, "reason": f"auto: {a.get('reason','')} | model: {m.get('reason','') if isinstance(m, dict) else ''}",
                       "auto": a["pass"], "model": (bool(m.get("pass", True)) if isinstance(m, dict) else bool(m))}
        accept = all(dims[d]["pass"] for d in EVAL_DIMS)
        fb = (model.get("actionable_feedback", "") if isinstance(model, dict) else "") or \
             ("Fix: " + "; ".join(f"{d}: {dims[d]['reason']}" for d in dims if not dims[d]["pass"]))
        return {"dims": dims, "accept": accept, "actionable_feedback": fb}
