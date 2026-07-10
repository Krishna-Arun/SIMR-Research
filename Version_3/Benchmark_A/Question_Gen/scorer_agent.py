"""
Scorer agent — GPT-OSS 20B.

Role in the question-generation loop: FINAL SCORE. Once the evaluator accepts a
question, the scorer assigns a final quality score and builds the answer rubric
used later to grade answering agents. It is the scoring authority for the
generated benchmark item.

STUB LEVEL: the prompt scaffolding and I/O contract are real; the rubric backend
and downstream persistence are not wired yet.
"""
from __future__ import annotations

import json

from backend import LocalLLM
import prompts

MODEL_KEY = "gpt-oss-20b"

SYSTEM = f"""You are the SCORER in a clinical-question-generation system.
You run ONLY on questions the Evaluator has already accepted. You assign a final
quality score and, more importantly, you build the GRADING RUBRIC that will later
be used to score answering agents on this question.

{prompts.full_spec()}

{prompts.REQUEST_RUBRIC}

YOUR RESTRICTIONS (Scorer):
  - Do NOT alter the question, options, golden set, or answer key.
  - Assign quality_score in [0,1] reflecting clinical soundness, difficulty, and
    how cleanly the golden set is necessary-and-sufficient.
  - Build a grading rubric that encodes, for the answering agent:
      * request_scoring: the 0 / 0.5 / 1 per-request justification rubric above,
      * golden_item_bonus: +1 for EACH requested item that is in the golden set
        (added to that item's justification score),
      * mc_correctness: how multi-select selection is scored against correct_options
        (including correctly choosing "None of the above"),
      * causal_answer: criteria for grading the final causal chain.
  - Return STRICT JSON only:
    {{"quality_score": float,
      "rubric": {{"request_scoring": {{...}}, "golden_set_bonus": float,
                 "mc_correctness": {{...}}, "causal_answer": [{{"criterion": str, "weight": float}}]}},
      "rationale": str}}
  - No prose outside the JSON."""

SCORE_TEMPLATE = """ACCEPTED QUESTION (JSON):
{question}

EVALUATOR RESULT (JSON):
{evaluation}

Score the question and build its rubric now."""


class ScorerAgent:
    def __init__(self, llm=None):
        # gpt-oss-20b uses the harmony chat format; the tokenizer template handles it.
        self.llm = llm or LocalLLM(MODEL_KEY)

    def score(self, question: str, evaluation: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": SCORE_TEMPLATE.format(
                question=question, evaluation=evaluation)},
        ]
        return self.llm.chat(messages, temperature=0.2)


if __name__ == "__main__":
    agent = ScorerAgent()
    print(agent.score(
        '{"question_text": "stub accepted question"}',
        '{"accept": true}'))
