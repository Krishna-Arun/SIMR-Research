"""Benchmark B evaluator — critiques a trajectory-prediction candidate on 4 dims (hybrid auto+model),
enforces direction-correctness against the data-derived ground truth, and bans buzzword leakage.
"""
from __future__ import annotations

import json
import re

from qgen.agentic_loop import run_agentic
from qgen.schema import EVAL_DIMS, VERDICT_TEMPLATE

_MECHANISM = ("->", "because", "due to", "leads to", "causes", "results in", "secondary to",
              "mechanism", "induces", "impairs", "clearance", "removes", "depletes", "shifts",
              "dilutes", "hemolysis", "fluid", "increas", "decreas", "reduc")
# Direction words that would leak the answer if present in the STEM. Word-boundary matched so common
# words don't false-positive (e.g. "follow-up" must not trip "up"); bare "up/down/drop" are excluded
# as too ambiguous — the leak-worthy terms are explicit trajectory words.
_DIR_RE = re.compile(r"\b(rising|falling|stable|unchanged|rise|fall|increas\w*|decreas\w*|"
                     r"trend\w*|worsen\w*|improv\w*|normaliz\w*|uptrend|downtrend)\b", re.I)


def _auto_checks(context: dict, candidate: dict) -> dict:
    truth = context.get("trajectories", {})
    per = {str(l.get("label")): l for l in candidate.get("per_lab", [])}
    targets = [t for t in (candidate.get("target_labs") or [])]
    qtext = str(candidate.get("question_text", "")).lower()

    # 1. answerable_from_pre_state: targets are real trajectory-able labs + direction correct
    real = [t for t in targets if t in truth]
    dir_ok = all(str(per.get(t, {}).get("expected_direction", "")).capitalize() == truth[t]["direction"]
                 for t in real) if real else False
    d1 = bool(real) and len(real) == len(targets) and dir_ok

    # 2. patient_specific: justifications reference concrete patient values (heuristic: a number)
    n_grounded = sum(1 for t in real if any(ch.isdigit() for ch in str(per.get(t, {}).get("causal_justification", ""))))
    d2 = n_grounded >= 1

    # 3. requires_causal_reasoning: justifications carry mechanism markers
    n_mech = sum(1 for t in real
                 if sum(m in str(per.get(t, {}).get("causal_justification", "")).lower() for m in _MECHANISM) >= 1)
    d3 = n_mech >= max(1, len(real) // 2)

    # 4. guideline_grounded precheck: each target lab has a pmid
    has_pmid = all(((per.get(t, {}).get("guideline_citation") or {}).get("pmid")) for t in real) if real else False
    d4 = has_pmid

    # anti-buzzword: stem must not reveal the predicted directions (word-boundary matched)
    leak_dir = bool(_DIR_RE.search(qtext))
    if leak_dir:
        d1 = False

    return {
        "answerable_from_pre_state": {"pass": d1, "reason": f"{len(real)}/{len(targets)} real labs; dir_correct={dir_ok}; dir_leak_in_stem={leak_dir}"},
        "patient_specific": {"pass": d2, "reason": f"{n_grounded} justifications cite a concrete value"},
        "requires_causal_reasoning": {"pass": d3, "reason": f"{n_mech}/{len(real)} have mechanism markers"},
        "guideline_grounded": {"pass": d4, "reason": f"all_targets_have_pmid={has_pmid}"},
    }


EVAL_INSTRUCTIONS = """You review a post-procedure trajectory-prediction question for THIS patient + procedure
on 4 dimensions, verifying guideline support via PubMed:
  1. answerable_from_pre_state — predictable from the PRE-procedure state + the procedure (causal physiology),
     and each lab's stated direction is physiologically correct for this procedure.
  2. patient_specific — justifications reference THIS patient's actual baseline values, not generic statements.
  3. requires_causal_reasoning — each justification is procedure -> mechanism -> lab (>=2 steps), not a guess.
  4. guideline_grounded — each lab's effect is supported by a REAL PubMed citation (verify PMIDs).

CRITICAL — NO BUZZWORD BINGO: the question stem must NOT reveal any predicted direction
(Rising/Falling/Stable or rise/fall/increase/decrease), must NOT name the diagnosis/answer, and must not
pile up buzzwords. If it does, FAIL answerable_from_pre_state and tell the writer to neutralize the stem.

Return {{"action":"final","result":<VERDICT>}} where VERDICT matches:
{template}"""


class EvaluatorAgent:
    def __init__(self, llm, dispatcher, mcp_tools, budget: int):
        self.llm, self.dispatcher, self.mcp_tools, self.budget = llm, dispatcher, mcp_tools, budget

    def evaluate(self, context: dict, candidate: dict) -> dict:
        auto = _auto_checks(context, candidate)
        forbidden = [str(context["subject_id"]), str(context["hadm_id"])]
        prompt = (f"CANDIDATE:\n{json.dumps(candidate, default=str)[:8000]}\n\n"
                  f"PROCEDURE: {context['procedure']['label']}\n"
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
