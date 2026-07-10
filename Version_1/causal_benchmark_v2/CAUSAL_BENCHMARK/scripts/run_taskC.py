"""
run_taskC.py  —  Task C counterfactual-outcome inference (LLMs).

For each cohort episode the model predicts the tracked outcomes (value + direction +
activation-derived confidence) under BOTH:
  - the factually-assigned treatment  (-> factual prediction, scored vs observed Y), and
  - the opposite treatment            (-> counterfactual prediction, scored vs the proxy).
pred_ITE = y(T=1) - y(T=0) is assembled downstream from these two by score_taskC.py.

Episode-level checkpointing + a wall-clock budget let a short GPU job resume on resubmission,
mirroring run_benchmark.py. Outputs predictions only; scoring lives in score_taskC.py so the
(expensive) LLM pass and the (cheap) metrics can be re-run independently.

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
import taskC_common as tc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ANSWERS = BENCH / "answers"
ANSWERS.mkdir(exist_ok=True)
SEL = BENCH / "data" / "outcome_selection.json"

FLIP = {"pci": "control", "control": "pci"}

# Per-outcome prediction descriptors (baseline filled per-episode at runtime).
DESCRIPTORS = {
    "peak_troponin_72h": {"id": "troponin", "display": "peak troponin T", "unit": "ng/mL",
                          "kind": "level", "positive": True,
                          "desc": "the peak troponin T over the 72h after the index time"},
    "delta_creatinine_72h": {"id": "creatinine", "display": "creatinine change", "unit": "mg/dL",
                             "kind": "delta", "positive": False,
                             "desc": "the change in creatinine (72h post-peak minus pre-index baseline)"},
    "peak_lactate_72h": {"id": "lactate", "display": "peak lactate", "unit": "mmol/L",
                         "kind": "level", "positive": False,
                         "desc": "the peak lactate over the 72h after the index time"},
    "peak_ckmb_72h": {"id": "ck_mb", "display": "peak CK-MB", "unit": "ng/mL",
                      "kind": "level", "positive": True,
                      "desc": "the peak CK-MB over the 72h after the index time"},
}


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


def _ep_descriptors(ep, tracked):
    """Tracked descriptors with this episode's per-marker baseline attached."""
    out = []
    for key in tracked:
        d = dict(DESCRIPTORS[key])
        d["key"] = key
        d["baseline"] = tc.marker_baseline(ep, key)
        out.append(d)
    return out


def run_one(model_name, backend, prompt_style, cohort, tracked, deadline):
    ckpt = ANSWERS / f"taskC_{model_name.replace('/', '_')}_{prompt_style}.json"
    preds = {}
    if ckpt.exists():
        try:
            preds = json.loads(ckpt.read_text()).get("predictions", {})
            log.info(f"  resumed: {len(preds)} episodes already predicted")
        except Exception as e:
            log.warning(f"  checkpoint unreadable, fresh start: {e}")

    todo = [ep for ep in cohort if ep["episode_id"] not in preds]
    if not todo:
        log.info("  fully cached — skipping model load")
        return preds, True
    log.info(f"  {len(todo)}/{len(cohort)} episodes to predict")

    try:
        predictor = create_predictor(model_name, prompt_style, backend)
    except Exception as e:
        log.error(f"  failed to load predictor: {e}")
        return preds, False

    def save():
        tmp = ckpt.with_suffix(".tmp")
        tmp.write_text(json.dumps({"model": model_name, "prompt_style": prompt_style,
                                   "backend": backend, "tracked_outcomes": tracked,
                                   "predictions": preds}, indent=2))
        tmp.replace(ckpt)

    finished = True
    for i, ep in enumerate(todo):
        if time.time() > deadline:
            log.info("  time budget hit — checkpointed, will resume on resubmit.")
            finished = False
            break
        fac = ep["intervention"]["type"]            # "pci" | "control"
        cf = FLIP.get(fac, "control")
        descs = _ep_descriptors(ep, tracked)
        try:
            pf = predictor.predict_scalar(ep, fac, descs, with_confidence=True)
            pc = predictor.predict_scalar(ep, cf, descs, with_confidence=True)
            preds[ep["episode_id"]] = {"arm": fac, "counterfactual_arm": cf,
                                       "factual": pf, "counterfactual": pc}
        except Exception as e:
            log.debug(f"  predict failed {ep['episode_id']}: {e}")
        if (i + 1) % 25 == 0:
            log.info(f"  {i + 1}/{len(todo)}")
            save()
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
    return preds, finished


def main():
    primary, secondary = tc.PRIMARY_OUTCOME_DEFAULT, "delta_creatinine_72h"
    if SEL.exists():
        sel = json.loads(SEL.read_text())
        primary = sel.get("primary_outcome", primary)
        secondary = sel.get("secondary_outcome", secondary)
    tracked = [o for o in dict.fromkeys([primary, secondary]) if o in DESCRIPTORS]
    log.info(f"Tracked outcomes: {tracked} (primary={primary})")

    _, episodes = tc.load_episodes()
    cohort = tc.taskC_cohort(episodes)
    cap = os.environ.get("CAUSAL_MAX_EPISODES")
    if cap and cap.isdigit():
        cohort = cohort[: int(cap)]
    log.info(f"Cohort: {len(cohort)} episodes")

    deadline = time.time() + int(os.environ.get("CAUSAL_TIME_BUDGET_S", "9300"))
    all_complete = True
    for model_name, backend in _models():
        for prompt_style in _prompts():
            if time.time() > deadline:
                all_complete = False
                break
            log.info(f"=== {model_name} ({backend}, {prompt_style}) ===")
            _, finished = run_one(model_name, backend, prompt_style, cohort, tracked, deadline)
            all_complete = all_complete and finished
        if time.time() > deadline:
            all_complete = False
            break

    sentinel = BENCH / "outputs" / "TASKC_ALL_COMPLETE"
    sentinel.parent.mkdir(exist_ok=True)
    if all_complete:
        sentinel.write_text(datetime.now().isoformat())
        log.info("✓ Task C inference complete (TASKC_ALL_COMPLETE written).")
    else:
        if sentinel.exists():
            sentinel.unlink()
        log.info("◴ Partial — checkpointed. Resubmit to resume.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
