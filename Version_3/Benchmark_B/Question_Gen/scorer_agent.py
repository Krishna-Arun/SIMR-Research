"""
Scorer agent — GPT-OSS 20B (Benchmark B).

Runs on accepted questions: assigns a quality score and emits the grading rubric
the answering-agent scorer will use — the per-lab direction rubric (1/0.5/0) plus
the causal-justification criteria. This rubric is designed to be ADDED onto the
Benchmark A answer-scoring rubric.
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts

MODEL_KEY = "gpt-oss-20b"

SYSTEM = f"""You are the SCORER in a lab-trajectory question-generation system.
You run only on accepted questions. Assign a quality score and build the grading
rubric used later to score answering agents on this question.

{prompts.full_spec()}

YOUR RESTRICTIONS (Scorer):
  - Do NOT change the question, targets, or ground-truth directions.
  - quality_score in [0,1] reflecting clinical soundness, direction balance
    (a good item is not mostly Stable), and causal clarity.
  - Build a rubric that encodes, for the answering agent:
      * direction_scoring: per target lab, 1.0 correct / 0.5 (actual up|down, predicted Stable)
        / 0.0 (opposite, or actual Stable and predicted a direction),
      * aggregate: mean of per-lab direction scores,
      * confidence: recorded for calibration only, NOT scored,
      * causal_justification: criteria for grading the agent's causal explanation.
  - Return STRICT JSON only:
    {{"quality_score": float,
      "rubric": {{"direction_scoring": {{...}}, "aggregate": str,
                 "confidence": "recorded, not scored",
                 "causal_justification": [{{"criterion": str, "weight": float}}]}},
      "rationale": str}}
  - No prose outside the JSON."""

SCORE_TEMPLATE = """ACCEPTED QUESTION (JSON incl. ground-truth directions):
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
