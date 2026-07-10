"""
run_taskC_multiarm.py  —  3-arm counterfactual inference (PCI / CABG / medical).

For every eligible patient the model predicts the durable outcomes (30-day mortality risk,
30-day readmission risk) UNDER EACH ARM, from the pre-index chart only. The factual arm's
prediction is scored vs the observed outcome; all three together give pairwise effects + a
best-arm recommendation (scored downstream by score_taskC_multiarm.py against the answer-key).

Joins data/context.json (clinical chart per hadm_id) with data/multiarm_cohort.json (arm +
durable outcomes + eligibility). Episode-level checkpointing + wall-clock budget (resumes on
resubmit), mirroring run_taskC.py. Outputs predictions only.

Env: CAUSAL_MODELS, CAUSAL_PROMPTS, CAUSAL_MAX_EPISODES, CAUSAL_TIME_BUDGET_S, CAUSAL_BACKEND.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "models"))
sys.path.insert(0, str(BENCH / "scripts"))

from llm_inference import create_predictor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CONTEXT = BENCH / "data" / "context.json"
COHORT = BENCH / "data" / "multiarm_cohort.json"
ANSWERS = BENCH / "answers"
ANSWERS.mkdir(exist_ok=True)

ARMS = ["pci", "cabg", "medical"]

# v1 prediction targets (probabilities): 30-day readmission (PRIMARY) + AKI (SECONDARY).
# Mortality is NOT predicted per-patient (too rare) — it's a population-level RCT anchor only.
DESCRIPTORS = [
    {"id": "readmit30", "key": "readmission_30d", "display": "risk of readmission within 30 days",
     "unit": "probability between 0 and 1", "kind": "level", "positive": False, "baseline": 0.20,
     "desc": "the probability (0 to 1) that the patient is readmitted within 30 days of discharge"},
    {"id": "aki", "key": "aki", "display": "risk of acute kidney injury",
     "unit": "probability between 0 and 1", "kind": "level", "positive": True, "baseline": 0.15,
     "desc": "the probability (0 to 1) of acute kidney injury (KDIGO) within 7 days of the index"},
]


def _models():
    env = os.environ.get("CAUSAL_MODELS", "").strip()
    backend = os.environ.get("CAUSAL_BACKEND", "huggingface").strip()
    if backend == "mock" or env == "mock":
        return [("mock", "mock")]
    if env:
        return [(m.strip(), backend) for m in env.split(",") if m.strip()]
    return [("Qwen/Qwen2.5-7B-Instruct", backend)]


def _prompts():
    env = os.environ.get("CAUSAL_PROMPTS", "").strip()
    return [p.strip() for p in env.split(",") if p.strip()] or ["zero_shot", "cot"]


def load_cohort():
    """Join context (chart) with cohort (arm + outcomes). Returns eligible episodes ready for the LLM."""
    if not CONTEXT.exists() or not COHORT.exists():
        log.error(f"need both {CONTEXT.name} and {COHORT.name} — run build_context + build_multiarm_cohort first")
        return []
    ctx = json.loads(CONTEXT.read_text())["context"]
    cohort = json.loads(COHORT.read_text())["episodes"]
    eps = []
    for c in cohort:
        if not c.get("eligible"):
            continue
        h = str(c["hadm_id"])
        if h not in ctx:
            continue
        cc = ctx[h]
        eps.append({
            "episode_id": f"ma_{c['arm']}_{h}",
            "hadm_id": c["hadm_id"],
            "factual_arm": c["arm"],
            "intervention": {"type": c["arm"], "index_time": cc.get("index_time", "the index time")},
            "clinical_context": cc["clinical_context"],
            "pre_context": {},                      # full labs live in clinical_context.labs_full
            "comorbidities": cc["comorbidities"],
        })
    return eps


def run_one(model_name, backend, prompt_style, eps, deadline):
    ckpt = ANSWERS / f"taskC_multiarm_{model_name.replace('/', '_')}_{prompt_style}.json"
    preds = {}
    if ckpt.exists():
        try:
            preds = json.loads(ckpt.read_text()).get("predictions", {})
            log.info(f"  resumed: {len(preds)} done")
        except Exception as e:
            log.warning(f"  bad checkpoint, fresh: {e}")
    todo = [e for e in eps if e["episode_id"] not in preds]
    if not todo:
        log.info("  fully cached")
        return True
    log.info(f"  {len(todo)}/{len(eps)} to predict")
    try:
        predictor = create_predictor(model_name, prompt_style, backend)
    except Exception as e:
        log.error(f"  predictor load failed: {e}")
        return False

    def save():
        tmp = ckpt.with_suffix(".tmp")
        tmp.write_text(json.dumps({"model": model_name, "prompt_style": prompt_style,
                                   "backend": backend, "arms": ARMS,
                                   "outcomes": [d["key"] for d in DESCRIPTORS],
                                   "predictions": preds}, indent=2))
        tmp.replace(ckpt)

    finished = True
    for i, ep in enumerate(todo):
        if time.time() > deadline:
            log.info("  time budget hit — checkpointed."); finished = False; break
        try:
            per_arm = predictor.predict_multiarm(ep, ARMS, DESCRIPTORS, with_confidence=True)
            preds[ep["episode_id"]] = {"hadm_id": ep["hadm_id"], "factual_arm": ep["factual_arm"],
                                       "predictions": per_arm}
        except Exception as e:
            log.debug(f"  predict failed {ep['episode_id']}: {e}")
        if (i + 1) % 20 == 0:
            log.info(f"  {i + 1}/{len(todo)}"); save()
    save()
    log.info(f"  predictions: {len(preds)}")
    try:
        del predictor
        import gc, torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    return finished


def main():
    eps = load_cohort()
    if not eps:
        return 1
    cap = os.environ.get("CAUSAL_MAX_EPISODES")
    if cap and cap.isdigit():
        eps = eps[: int(cap)]
    from collections import Counter
    log.info(f"Eligible episodes: {len(eps)}  arms: {dict(Counter(e['factual_arm'] for e in eps))}")

    deadline = time.time() + int(os.environ.get("CAUSAL_TIME_BUDGET_S", "9300"))
    all_done = True
    for model_name, backend in _models():
        for prompt_style in _prompts():
            if time.time() > deadline:
                all_done = False
                break
            log.info(f"=== {model_name} ({backend}, {prompt_style}) ===")
            all_done = run_one(model_name, backend, prompt_style, eps, deadline) and all_done
        if time.time() > deadline:
            all_done = False
            break

    sentinel = BENCH / "outputs" / "TASKC_MULTIARM_COMPLETE"
    sentinel.parent.mkdir(exist_ok=True)
    if all_done:
        sentinel.write_text(datetime.now().isoformat())
        log.info("✓ multi-arm inference complete.")
    elif sentinel.exists():
        sentinel.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
