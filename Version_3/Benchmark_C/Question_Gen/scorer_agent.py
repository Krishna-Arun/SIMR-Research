"""
Scorer agent — GPT-OSS 20B (Benchmark C).

Runs on accepted questions: quality score + the grading rubric for answering
agents — the 0/1 identification rule plus causal-justification criteria. Designed
to be ADDED onto the Benchmark A answer-scoring rubric.
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts

MODEL_KEY = "gpt-oss-20b"

SYSTEM = f"""You are the SCORER in an intervention-attribution question-generation system.
You run only on accepted questions. Assign a quality score and build the grading rubric.

{prompts.full_spec()}

YOUR RESTRICTIONS (Scorer):
  - Do NOT change the question, pairing, or the answer.
  - quality_score in [0,1] reflecting how cleanly the two procedures' effects diverge on
    the shared labs, how similar the baselines are (harder = better), and causal clarity.
  - Build a rubric that encodes, for the answering agent:
      * identification: 1 if chosen_patient == answer else 0,
      * confidence: recorded for calibration, NOT scored,
      * causal_justification: criteria for grading the agent's causal explanation.
  - Return STRICT JSON only:
    {{"quality_score": float,
      "rubric": {{"identification": "1 if chosen_patient==answer else 0",
                 "confidence": "recorded, not scored",
                 "causal_justification": [{{"criterion": str, "weight": float}}]}},
      "rationale": str}}
  - No prose outside the JSON."""

SCORE_TEMPLATE = """ACCEPTED QUESTION (JSON incl. answer):
{question}

EVALUATOR RESULT (JSON):
{evaluation}

Score and build the rubric now."""


class ScorerAgent:
    def __init__(self, llm=None):
        self.llm = llm or LocalLLM(MODEL_KEY)

    def score(self, question: str, evaluation: str) -> str:
        return self.llm.chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": SCORE_TEMPLATE.format(
                question=question, evaluation=evaluation)},
        ], temperature=0.2)


if __name__ == "__main__":
    print(ScorerAgent().score('{"stem": "stub"}', '{"accept": true}'))
