"""
score_taskC_multiarm.py  —  score 3-arm predictions (readmission primary, AKI secondary).

Consumes answers/taskC_multiarm_*.json (per-patient, per-arm predicted probabilities) + the
observed outcomes in data/multiarm_cohort.json. Computes the PROXY-FREE headline block now;
the answer-key block (pairwise effects, best-arm accuracy) fills in when data/answerkey_multiarm.json
exists (built later by the causal forest).

PROXY-FREE (real, no counterfactual needed):
  - factual AUC / Brier / calibration ECE : the model's predicted risk under the FACTUAL arm vs
                                            the observed outcome.
  - intervention spread                   : how much the prediction moves across arms (does the
                                            model condition on the treatment at all?).
  - best-arm recommendation mix           : what the model would choose (sanity / behavior).
VS ANSWER-KEY (when present): pairwise effect sign/PEHE, best-arm accuracy, ranking.

Outputs: outputs/taskC_multiarm_results.json + outputs/TASKC_MULTIARM_RESULTS.md
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "metrics"))
import multiarm_metrics as mm
import justification_rubric as jr

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

COHORT = BENCH / "data" / "multiarm_cohort.json"
CONTEXT = BENCH / "data" / "context.json"
ANSWERKEY = BENCH / "data" / "answerkey_multiarm.json"
ANSWERS = BENCH / "answers"
OUTPUTS = BENCH / "outputs"
OUTPUTS.mkdir(exist_ok=True)

ARMS = ["pci", "cabg", "medical"]
OUTCOME_MAP = {"readmit30": "readmission_30d", "aki": "aki"}   # prediction id -> observed key


def _auc(p, y):
    try:
        from sklearn.metrics import roc_auc_score
        if len(set(y)) < 2:
            return None
        return round(float(roc_auc_score(y, p)), 4)
    except Exception:
        return None


def _brier(p, y):
    return round(float(np.mean((np.asarray(p) - np.asarray(y)) ** 2)), 4) if p else None


def _ece(p, y, bins=10):
    p, y = np.asarray(p, float), np.asarray(y, float)
    if len(p) == 0:
        return None
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for i in range(bins):
        hi = p <= edges[i + 1] if i == bins - 1 else p < edges[i + 1]
        m = (p >= edges[i]) & hi
        if m.sum():
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return round(float(e), 4)


def load_observed():
    d = json.loads(COHORT.read_text())
    obs = {}
    for e in d["episodes"]:
        if e.get("eligible"):
            obs[int(e["hadm_id"])] = {"readmission_30d": e.get("readmission_30d"),
                                      "aki": e.get("aki"), "arm": e["arm"]}
    return obs


def score_model(preds, obs, answerkey, ctx):
    res = {"n": len(preds), "outcomes": {}}
    for oid, okey in OUTCOME_MAP.items():
        fp, yy, spreads, rec_arms = [], [], [], []
        just_scores, just_reasons = [], []
        for eid, p in preds.items():
            h = int(p["hadm_id"])
            fac = p["factual_arm"]
            per_arm = p["predictions"]
            o = obs.get(h, {})
            y = o.get(okey)
            fv = per_arm.get(fac, {}).get(oid, {}).get("value")
            if y is not None and fv is not None:
                fp.append(float(fv)); yy.append(int(y))
            arm_vals = {a: per_arm.get(a, {}).get(oid, {}).get("value") for a in ARMS}
            arm_vals = {a: v for a, v in arm_vals.items() if v is not None}
            if len(arm_vals) >= 2:
                spreads.append(max(arm_vals.values()) - min(arm_vals.values()))
                rec_arms.append(min(arm_vals, key=arm_vals.get))   # lower risk = preferred
            # justification rubric (0/0.5/1) per arm's justification for this outcome
            c = ctx.get(h)
            if c:
                ref_dir = None  # answer-key effect direction (per-arm) not wired yet -> caps at 0.5
                for a in ARMS:
                    e = per_arm.get(a, {}).get(oid, {})
                    s = jr.score_justification(e.get("justification", ""), c, e.get("direction"),
                                               ref_direction=ref_dir, outcome_id=oid)
                    just_scores.append(s["score"]); just_reasons.append(s["reason"])
        block = {"n_factual": len(fp), "factual_auc": _auc(fp, yy),
                 "factual_brier": _brier(fp, yy), "calibration_ece": _ece(fp, yy),
                 "mean_intervention_spread": round(float(np.mean(spreads)), 4) if spreads else None,
                 "best_arm_mix": {a: round(rec_arms.count(a) / len(rec_arms), 3) for a in ARMS} if rec_arms else {}}
        if just_scores:
            from collections import Counter
            n = len(just_scores)
            block["justification"] = {
                "mean": round(float(np.mean(just_scores)), 3), "n": n,
                "dist": {str(k): round(sum(1 for s in just_scores if s == k) / n, 3) for k in (0.0, 0.5, 1.0)},
                "top_reasons": dict(Counter(just_reasons).most_common(4))}
        # answer-key block (pairwise effects + best-arm accuracy) when available
        if answerkey and oid in answerkey:
            ak = answerkey[oid]
            pred_eff, ref_eff = [], []
            pred_best, ref_best = [], []
            for eid, p in preds.items():
                h = str(p["hadm_id"])
                if h not in ak:
                    continue
                per_arm = {a: p["predictions"].get(a, {}).get(oid, {}).get("value") for a in ARMS}
                # primary contrast pci - medical
                if per_arm.get("pci") is not None and per_arm.get("medical") is not None \
                        and ak[h].get("pci_vs_medical") is not None:
                    pred_eff.append(per_arm["pci"] - per_arm["medical"])
                    ref_eff.append(ak[h]["pci_vs_medical"])
                if ak[h].get("best_arm"):
                    pb = mm.best_arm({a: v for a, v in per_arm.items() if v is not None})
                    if pb:
                        pred_best.append(pb); ref_best.append(ak[h]["best_arm"])
            block["pci_vs_medical_sign"] = mm.pairwise_sign_agreement(pred_eff, ref_eff)
            block["pci_vs_medical_pehe"] = mm.pairwise_pehe(pred_eff, ref_eff)
            block["best_arm_accuracy"] = mm.best_arm_accuracy(pred_best, ref_best)
        res["outcomes"][oid] = block
    return res


def main():
    if not COHORT.exists():
        log.error("multiarm_cohort.json missing — run build_multiarm_cohort.py first")
        return 1
    obs = load_observed()
    ctx = {}
    if CONTEXT.exists():
        ctx = {int(k): v for k, v in json.loads(CONTEXT.read_text())["context"].items()}
    answerkey = json.loads(ANSWERKEY.read_text()) if ANSWERKEY.exists() else None
    log.info(f"Observed outcomes for {len(obs)} eligible patients; "
             f"answer-key: {'present' if answerkey else 'NOT YET (proxy-free metrics only)'}")

    results = {"task": "multiarm_revascularization", "primary_outcome": "readmission_30d",
               "secondary_outcome": "aki", "answerkey_present": bool(answerkey), "methods": {}}
    for f in sorted(ANSWERS.glob("taskC_multiarm_*.json")):
        if f.suffix == ".tmp":
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        preds = d.get("predictions", {})
        if not preds:
            continue
        name = f"{d.get('model','?')} [{d.get('prompt_style','?')}]"
        results["methods"][name] = score_model(preds, obs, answerkey, ctx)
        log.info(f"scored {name}: n={len(preds)}")

    (OUTPUTS / "taskC_multiarm_results.json").write_text(json.dumps(results, indent=2))
    write_report(results)
    log.info(f"Wrote {OUTPUTS/'taskC_multiarm_results.json'} + TASKC_MULTIARM_RESULTS.md")
    return 0


def _g(d, *path, default="—"):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return default
    return d


def write_report(results):
    L = [f"# Task C (multi-arm) — PCI vs CABG vs medical", "",
         f"**Generated:** {datetime.now().isoformat()}",
         f"**Primary:** readmission_30d   **Secondary:** AKI   "
         f"**Answer-key:** {'present' if results['answerkey_present'] else 'pending (proxy-free only)'}", ""]
    for oid in ["readmit30", "aki"]:
        L += [f"## Outcome: {oid}", "",
              "| Method | n | factual AUC | calib ECE | interv. spread | best-arm mix | justif. (0/.5/1) | sign vs key | best-arm acc |",
              "|---|---|---|---|---|---|---|---|---|"]
        for name, r in results["methods"].items():
            b = r["outcomes"].get(oid, {})
            mix = b.get("best_arm_mix") or {}
            mix_s = "/".join(f"{mix.get(a,0):.2f}" for a in ARMS) if mix else "—"
            j = b.get("justification") or {}
            jd = j.get("dist") or {}
            j_s = (f"{j.get('mean')} ({jd.get('0.0','?')}/{jd.get('0.5','?')}/{jd.get('1.0','?')})"
                   if j else "—")
            L.append(f"| {name} | {b.get('n_factual')} | {b.get('factual_auc')} | "
                     f"{b.get('calibration_ece')} | {b.get('mean_intervention_spread')} | {mix_s} | "
                     f"{j_s} | {_g(b,'pci_vs_medical_sign','sign_agree')} | "
                     f"{_g(b,'best_arm_accuracy','acc')} |")
        L.append("")
    L += ["## Notes", "",
          "- **factual AUC/Brier/ECE**: predicted risk under the arm the patient actually got, vs the "
          "observed outcome — fully real, no counterfactual assumptions.",
          "- **interv. spread**: mean (max−min) of predicted risk across the 3 arms; ~0 means the model "
          "ignores the treatment.  **best-arm mix**: pci/cabg/medical share of recommendations.",
          "- **sign/PEHE/best-arm acc** vs the causal-forest answer-key (blank until it's built); these are "
          "*agreement-with-estimator*, scored only on each contrast's common-support patients.",
          "- **justif. (0/.5/1)** = worded-justification rubric: mean score + fraction at each level "
          "(0 nonsense / 0.5 general / 1 patient-specific + causally verified). Grounding & causal-"
          "direction are automatic; coherence via judge. **Ceiling is 0.5 until the answer-key lands** "
          "(can't confirm 'causally verified' without a reference direction).",
          "- Mortality is reported separately as a population ATE-vs-RCT check (too rare for per-patient)."]
    (OUTPUTS / "TASKC_MULTIARM_RESULTS.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
