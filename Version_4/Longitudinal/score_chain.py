#!/usr/bin/env python3
"""
Version_4 AGENT-BASED scoring harness for the chained benchmark (a -> b -> c -> d).

Per the user's requirement, an EVALUATOR AGENT (GPT-OSS-20B by default) grades every
causal / open-ended / justification dimension with the 0 / 0.5 / 1 rubric:
    0   irrelevant, inaccurate, or nonsensical
    0.5 accurate but GENERIC / textbook — not patient-specific
    1   patient-specific causal links citing THIS patient's quantitative values

Objective sub-scores stay deterministic against data-derived ground truth:
    b  per-selected-lab direction  (TIGHTENED: 1 correct / 0 otherwise — no Stable-hedge)
    c  patient identification       (1 if chosen == answer else 0)
    d  mortality call correctness   (+ Brier calibration from stated confidence)

A step reaches FULL CAUSAL CREDIT only when its objective part is correct AND the agent gives
the justification a 1.0. The headline difficulty metric is the fraction of cases/steps at full
credit (target <20%). `total` is the RL reward used by GRPO.

Reliability: pass --judges to run several judge configs (seeds/temperatures and/or a second
judge model); reliability.py consumes the per-judge scores to compute Cronbach's alpha + kappa.

Usage:
  SIMR_BACKEND=ollama python score_chain.py --answers outputs_v4/answers_<model>.jsonl \
      --judge gpt-oss-20b [--judge-runs 1]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs_v4"
CHAINED = OUT / "chained.jsonl"
QGEN = HERE.parent / "Benchmark_a"                     # backend.py lives here
sys.path.insert(0, str(QGEN))

DIRS = {"rising", "falling", "stable"}


# ── judge agent ──────────────────────────────────────────────────────────────
class Judge:
    """GPT-OSS-20B (default) scoring a single dimension 0/0.5/1 with a rationale."""
    def __init__(self, model_key="gpt-oss-20b", temperature=0.2):
        from backend import LocalLLM
        self.llm = LocalLLM(model_key)
        self.temperature = temperature

    def score(self, task: str, answer: str, reference: str, criterion: str) -> dict:
        prompt = (
            "You are a strict clinical-reasoning grader. Score the CANDIDATE ANSWER on ONE "
            "criterion using this rubric:\n"
            "  0   = irrelevant, inaccurate, or nonsensical\n"
            "  0.5 = accurate but GENERIC/textbook, NOT specific to this patient's data\n"
            "  1   = patient-specific causal reasoning that cites THIS patient's quantitative "
            "values and forms a >=2-step causal chain\n\n"
            f"CRITERION: {criterion}\n\nTASK GIVEN TO THE MODEL:\n{task[:1500]}\n\n"
            f"HIDDEN REFERENCE (ground truth / ideal):\n{reference[:1200]}\n\n"
            f"CANDIDATE ANSWER:\n{answer[:2500]}\n\n"
            'Reply with STRICT JSON only: {"score": 0 | 0.5 | 1, "rationale": "<one sentence>"}')
        try:
            out = self.llm.chat([{"role": "user", "content": prompt}],
                                temperature=self.temperature, max_new_tokens=3000)
            m = re.search(r"\{.*\}", out, re.DOTALL)
            obj = json.loads(m.group(0)) if m else {}
            sc = float(obj.get("score", 0))
            sc = min({0.0, 0.5, 1.0}, key=lambda x: abs(x - sc))
            return {"score": sc, "rationale": obj.get("rationale", "")}
        except Exception as e:
            return {"score": 0.0, "rationale": f"judge-error: {type(e).__name__}"}


# ── objective sub-scores ─────────────────────────────────────────────────────
def _dir_score_tight(pred, true):
    return 1.0 if str(pred).strip().capitalize() == true else 0.0


def _brier(conf, label_yes):
    try:
        p = float(conf)
    except (TypeError, ValueError):
        p = 0.5
    y = 1.0 if label_yes else 0.0
    return (p - y) ** 2


# ── per-case scoring ─────────────────────────────────────────────────────────
def score_case(record, answer, judge: Judge):
    steps, ans = record["steps"], answer.get("steps", {})
    per = {}

    # a — open-ended intervention + agentic requests
    a, aa = steps["a"], ans.get("a", {}) or {}
    ref_a = (f"correct intervention family = {a['reference_answer']['family']}, "
             f"procedure = {a['reference_answer'].get('procedure')}. "
             f"golden labs = {[g.get('lab') for g in a.get('golden_labs', [])]}")
    ans_text = json.dumps({k: aa.get(k) for k in ("answer", "causal_chain", "evidence")})[:2500]
    j_answer = judge.score(a["stem"], ans_text, ref_a,
                           "correctness of the chosen intervention AND patient-specific causal "
                           "chain citing retrieved lab values")
    # request quality: judge the justifications, + deterministic golden-membership bonus
    golden_names = {str(g.get("lab", "")).lower() for g in a.get("golden_labs", [])}
    reqs = aa.get("requests", []) or []
    req_scores = []
    for r in reqs[:2]:                                   # cap judged requests (GPT-OSS is slow)
        item = str(r.get("item", "")); just = str(r.get("justification", ""))
        jq = judge.score(a["stem"], f"requested '{item}' because: {just}", ref_a,
                         "is this data request justified specifically for THIS patient")["score"]
        bonus = 1.0 if any(g and g in item.lower() for g in golden_names) else 0.0
        req_scores.append(min(1.0, jq) + bonus)
    per["a"] = {"answer": j_answer["score"], "answer_rationale": j_answer["rationale"],
                "request_quality_mean": round(sum(req_scores) / len(req_scores), 3) if req_scores else 0.0,
                "n_requests": len(reqs),
                "golden_recall": round(len([1 for r in reqs
                                            if any(g and g in str(r.get('item', '')).lower()
                                                   for g in golden_names)]) / max(len(golden_names), 1), 3),
                "full_credit": j_answer["score"] == 1.0}

    # b — trajectory: tightened direction + judged justification
    b, ab = steps["b"], ans.get("b", {}) or {}
    truth = {t["lab"]: t["direction"] for t in b.get("ground_truth", [])}
    sel = ab.get("selected", []) or []
    dir_hits, just_scores = [], []
    for s in sel:
        lab = s.get("lab");
        if lab in truth:
            dir_hits.append(_dir_score_tight(s.get("direction"), truth[lab]))
    if sel:
        jb = judge.score(b["stem"], json.dumps(sel)[:2000],
                         f"true directions: {truth}",
                         "per-lab causal justification quality for the predicted trajectories")
        just_scores.append(jb["score"])
    dir_acc = sum(dir_hits) / len(dir_hits) if dir_hits else 0.0
    per["b"] = {"direction_acc": round(dir_acc, 3), "n_scored": len(dir_hits),
                "all_correct": bool(dir_hits) and all(h == 1.0 for h in dir_hits),
                "justification": just_scores[0] if just_scores else 0.0,
                "full_credit": bool(dir_hits) and all(h == 1.0 for h in dir_hits)
                               and (just_scores[0] if just_scores else 0) == 1.0}

    # c — attribution: deterministic ID AND judged mechanism
    c, ac = steps.get("c"), ans.get("c", {}) or {}
    if c:
        correct = str(ac.get("chosen", "")).strip().upper()[:1] == str(c["answer"]).upper()
        jc = judge.score(c["stem"], str(ac.get("mechanism", ""))[:2000],
                         f"correct patient = {c['answer']}",
                         "causal physiological mechanism distinguishing the two interventions")
        per["c"] = {"identification": 1.0 if correct else 0.0, "mechanism": jc["score"],
                    "full_credit": correct and jc["score"] == 1.0}

    # d — mortality: correctness + calibration + judged rationale
    d, ad = steps["d"], ans.get("d", {}) or {}
    call = str(ad.get("call", "")).strip().capitalize()
    correct_d = call == d["correct"]
    brier = _brier(ad.get("confidence"), d["correct"] == "Yes")
    jd = judge.score(d["stem"], str(ad.get("rationale", ""))[:2000],
                     f"true 1-year mortality = {d['correct']}",
                     "causal risk rationale referencing the patient's abnormal values/trends")
    per["d"] = {"correct": 1.0 if correct_d else 0.0, "brier": round(brier, 3),
                "rationale": jd["score"], "full_credit": correct_d and jd["score"] == 1.0}

    # aggregate scalar reward (mean of the headline sub-score per step)
    head = [per["a"]["answer"],
            per["b"]["direction_acc"],
            per.get("c", {}).get("identification", None),
            per["d"]["correct"]]
    head = [h for h in head if h is not None]
    total = round(sum(head) / len(head), 4) if head else 0.0
    fully_solved = all(per[s].get("full_credit") for s in ("a", "b", "d")) and \
        (per.get("c", {}).get("full_credit", True))
    return {"per_step": per, "total": total, "fully_solved": fully_solved}


def run(answers_path, judge_key, judge_runs):
    records = {json.loads(l)["question_id"]: json.loads(l)
               for l in open(CHAINED) if l.strip()}
    answers = {json.loads(l)["question_id"]: json.loads(l)
               for l in open(answers_path) if l.strip()}
    judge = Judge(judge_key)
    results = []
    for qid, ans in answers.items():
        rec = records.get(qid)
        if not rec:
            continue
        runs = [score_case(rec, ans, judge) for _ in range(judge_runs)]
        # average the scalar across judge runs; keep run 0's detail
        avg_total = round(sum(r["total"] for r in runs) / len(runs), 4)
        res = runs[0]; res["total_mean_over_judges"] = avg_total
        res["judge_totals"] = [r["total"] for r in runs]
        res["question_id"] = qid; res["arm"] = rec["anchor"]["family"]
        results.append(res)
        print(f"{qid} [{res['arm']}] total={avg_total} "
              f"a.ans={res['per_step']['a']['answer']} b.dir={res['per_step']['b']['direction_acc']} "
              f"d.ok={res['per_step']['d']['correct']} solved={res['fully_solved']}", flush=True)

    n = len(results) or 1
    def frac(f): return round(sum(1 for r in results if f(r)) / n, 3)
    summary = {"n": len(results), "judge": judge_key, "judge_runs": judge_runs,
               "mean_total": round(sum(r["total_mean_over_judges"] for r in results) / n, 4),
               "a_answer_full_credit_rate": frac(lambda r: r["per_step"]["a"]["full_credit"]),
               "b_all_correct_rate": frac(lambda r: r["per_step"]["b"]["all_correct"]),
               "d_correct_rate": frac(lambda r: r["per_step"]["d"]["correct"] == 1.0),
               "fully_solved_rate": frac(lambda r: r["fully_solved"]),
               "mean_brier_d": round(sum(r["per_step"]["d"]["brier"] for r in results) / n, 4)}
    outp = OUT / (Path(answers_path).stem + f".scored.{judge_key}.json")
    outp.write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    print("\n=== v4 chain scoring summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"saved -> {outp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--judge", default="gpt-oss-20b")
    ap.add_argument("--judge-runs", type=int, default=1)
    args = ap.parse_args()
    run(args.answers, args.judge, args.judge_runs)
