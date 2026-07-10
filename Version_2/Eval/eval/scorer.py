"""Scoring agent for Phase-2 evaluation.

- Benchmark A: an LLM judge (gpt-oss) grades the agent's lab-request (0/0.5/1) and answer (0/0.5/1).
- Benchmark B: deterministic per-lab direction score (1/0.5/0) vs the data-derived true_direction.
- Benchmark C: deterministic 0/1 on the chosen patient.
ECE (calibration) is computed by the run aggregator over (confidence, correct) pairs.

The LLM judge is a RUTHLESS MENTOR (per user): grade harshly, stress-test, reward only rigorous,
patient-specific, evidence-grounded reasoning — never generic/hand-wavy answers.
"""
from __future__ import annotations
import json

RUTHLESS_MENTOR = (
    "Be my ruthless mentor. If my ideas are trash, grade harshly. Stress-test everything. "
    "I need bulletproof thinking, not validation."
)

JUDGE_A_SYS = RUTHLESS_MENTOR + """

You are scoring an AI agent's response to a CARDIOVASCULAR benchmark question. The agent had to (1) REQUEST
the right labs/microbiology for THIS patient and (2) ANSWER with patient-specific causal reasoning.

Score TWO things, each 0 / 0.5 / 1, defaulting to the LOWER score whenever reasoning is generic, not
patient-specific, or unsupported by the requested labs:

LAB-REQUEST score:
 0 = nonsensical, irrelevant, or inaccurate requests
 0.5 = accurate but generic/textbook requests, not tied to THIS patient
 1 = justifies each lab's necessity in THIS patient's context AND uses multiple labs toward the answer

ANSWER score (diagnosis or intervention):
 0 = nonsensical, irrelevant, or inaccurate
 0.5 = generic causal links; does not use the requested labs appropriately (or at all)
 1 = patient-specific causal links using the labs (and external evidence) as evidence

Compare against the GOLD answer key but do NOT reward an answer just for matching keywords — demand real,
patient-grounded causal reasoning. Output ONLY JSON: {"lab_request_score":0|0.5|1,"answer_score":0|0.5|1,
"rationale":"<=2 sentences, specific about what was missing"}."""


def judge_a(judge_llm, question_text, gold, agent_requested, agent_answer) -> dict:
    """gold = the question record (reference_answer, gold_labs, causal_chain)."""
    gl = ", ".join(g.get("label", "") for g in gold.get("gold_labs", []))
    user = (f"QUESTION:\n{question_text}\n\n"
            f"GOLD reference answer: {gold.get('reference_answer','')}\n"
            f"GOLD labs (the labs that should be requested): {gl}\n"
            f"GOLD causal chain: {gold.get('causal_chain')}\n\n"
            f"AGENT requested labs: {agent_requested}\n"
            f"AGENT answer: {agent_answer}\n\n"
            "Score now. Output ONLY the JSON.")
    out = judge_llm.chat([{"role": "system", "content": JUDGE_A_SYS},
                          {"role": "user", "content": user}]).text
    return _loose(out, {"lab_request_score": 0, "answer_score": 0, "rationale": "unparseable judge output"})


def score_b(true_by_lab: dict, agent_pred: dict) -> dict:
    """true_by_lab: {lab: 'Rising|Falling|Stable'}; agent_pred: {lab: 'Rising|Falling|Stable'}.
    1 correct; 0.5 if true is non-stable but agent said Stable; 0 otherwise (or any dir when true=Stable)."""
    per = {}
    for lab, true_d in true_by_lab.items():
        p = str(agent_pred.get(lab, "")).strip().capitalize()
        t = str(true_d).strip().capitalize()
        if p == t:
            per[lab] = 1.0
        elif t != "Stable" and p == "Stable":
            per[lab] = 0.5
        else:
            per[lab] = 0.0
    mean = sum(per.values()) / len(per) if per else 0.0
    return {"per_lab": per, "mean": mean, "n": len(per)}


def score_c(true_owner: str, agent_choice: str) -> dict:
    correct = str(agent_choice).strip().upper()[:1] == str(true_owner).strip().upper()[:1]
    return {"correct": int(correct)}


def ece(pairs, n_bins: int = 10) -> float:
    """pairs = [(confidence in [0,1], correct in {0,1})]. Expected Calibration Error."""
    pairs = [(max(0.0, min(1.0, float(c))), int(k)) for c, k in pairs if c is not None]
    if not pairs:
        return float("nan")
    N = len(pairs)
    tot = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        bucket = [(c, k) for c, k in pairs if (lo < c <= hi) or (b == 0 and c == 0)]
        if not bucket:
            continue
        conf = sum(c for c, _ in bucket) / len(bucket)
        acc = sum(k for _, k in bucket) / len(bucket)
        tot += (len(bucket) / N) * abs(acc - conf)
    return tot


def _loose(text: str, default: dict) -> dict:
    import re
    for frag in re.findall(r"\{.*?\}", text or "", re.DOTALL)[::-1]:
        try:
            return json.loads(frag)
        except Exception:
            continue
    return default
