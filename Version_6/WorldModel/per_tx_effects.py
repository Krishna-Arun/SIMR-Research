#!/usr/bin/env python3
"""
Per-treatment causal effects for all 6 treatments (finishes #2 across the action space).

Design (a first, honest, IPW causal contrast):
  - anchor everyone at ICU admission (t0); outcome = each lab nearest +72h
  - treatment T = started within first 48h (vs not)
  - confounders = comorbidities + age + sex + baseline labs
  - report naive vs IPW-adjusted effect  (treated - control) per lab
Caveats: coarse "got-T-in-48h vs not" contrast; positivity is thin for rare treatments
(dialysis/inotrope); this is the causal baseline, not a validated per-patient effect.
"""
import json, os
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
LABS = ["Creatinine", "BUN (Urea Nitrogen)", "Potassium", "Bicarbonate"]
COMORB = ["aki", "ckd_nonesrd", "diabetes", "sepsis", "hypertension", "cardiogenic_shock", "atrial_fib", "cad", "copd", "liver_disease"]
TREATMENTS = ["diuretic", "vasodilator", "inotrope", "vasopressor", "dialysis", "ventilation"]


def near(traj, target=72.0, lo=48.0, hi=96.0):
    cand = [(abs(h - target), v) for h, v, *_ in traj if lo <= h <= hi]
    return min(cand)[1] if cand else np.nan


def main():
    recs = [json.loads(l) for l in open(os.path.join(HERE, "multitx_cohort.jsonl"))]
    # baseline lab scaler from cohort
    bl = {lab: [r["baseline_labs"][lab] for r in recs if lab in r["baseline_labs"]] for lab in LABS}
    scal = {lab: (np.mean(v), np.std(v) + 1e-6) for lab, v in bl.items()}

    def conf(r):
        c = [1.0 if r["comorbidities"].get(k) else 0.0 for k in COMORB]
        c += [(r["age"] or 65) / 100.0, 1.0 if r["sex"] == "M" else 0.0]
        for lab in LABS:
            v = r["baseline_labs"].get(lab)
            c.append((v - scal[lab][0]) / scal[lab][1] if v is not None else 0.0)
        return c

    C = np.array([conf(r) for r in recs])
    # outcomes per lab (nearest +72h)
    Y = {lab: np.array([near(r["lab_traj"].get(lab, [])) for r in recs], dtype=float) for lab in LABS}

    print(f"n={len(recs)} admissions\n")
    print(f"{'treatment':12s} {'n_trt':>6} {'AUC':>6} | " + " ".join(f"{l.split()[0]:>18}" for l in LABS))
    print(f"{'':12s} {'':>6} {'':>6} | " + " ".join(f"{'naive / IPW':>18}" for _ in LABS))
    print("-" * 96)
    for t in TREATMENTS:
        T = np.array([r["treatments"][t] for r in recs])
        if T.sum() < 30:
            continue
        ps = LogisticRegression(max_iter=1000).fit(C, T)
        p = np.clip(ps.predict_proba(C)[:, 1], 1e-3, 1 - 1e-3)
        auc = roc_auc_score(T, p)
        pT = T.mean()
        w = np.where(T == 1, pT / p, (1 - pT) / (1 - p)).clip(0.1, 10)
        cells = []
        for lab in LABS:
            y = Y[lab]; ok = ~np.isnan(y)
            t1 = ok & (T == 1); t0 = ok & (T == 0)
            naive = y[t1].mean() - y[t0].mean()
            ipw = (y[t1] * w[t1]).sum() / w[t1].sum() - (y[t0] * w[t0]).sum() / w[t0].sum()
            cells.append(f"{naive:+7.2f}/{ipw:+7.2f}")
        print(f"{t:12s} {int(T.sum()):6d} {auc:6.2f} | " + " ".join(f"{c:>18}" for c in cells))
    print("\n(each cell: naive effect / IPW-adjusted effect on the +72h lab, treated - control)")
    print("IPW column = the DAG-adjusted causal effect of each treatment on each lab.")


if __name__ == "__main__":
    main()
