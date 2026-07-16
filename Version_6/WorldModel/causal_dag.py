#!/usr/bin/env python3
"""
DAG-based causal-inference layer (approach #2: DAG selects confounders).

The DAG for the treatment decision:

    confounders C ──(indication)──► TREATMENT T ──► OUTCOME Y (post labs)
         └──────────(prognosis)───────────────────►

By the backdoor criterion, adjusting for the BASELINE confounders C (pre-anchor,
pre-treatment) blocks the confounding path. We deliberately DO NOT adjust for any
post-treatment variable (those are mediators/colliders and would induce bias).

Adjustment set C  (all measured at/ before the anchor):
    baseline creatinine, BUN, potassium, bicarbonate
    comorbidity flags (aki, ckd, diabetes, sepsis, htn, shock, afib, cad, copd, liver)
    age, sex

Deliverables:
  1. propensity model  P(T=dialysis | C)   -> IPW weights
  2. covariate balance (SMD) before vs after IPW  -> did adjustment work?
  3. g-computation / IPW estimate of the dialysis-vs-diuretic effect on post labs
     -> an INDEPENDENT causal baseline to compare against the world model
"""
import numpy as np
import wm_data as D
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

CONF_LABS = D.TARGET_LABS
COMORB = D.COMORBID


def confounders(e, scaler):
    """Baseline adjustment-set vector C for one patient (the DAG's backdoor set)."""
    bl = [(e["bval"][j] if e["bval"][j] is not None else scaler["lab"]["LAB:" + l if False else l][0])
          for j, l in enumerate(CONF_LABS)]
    # standardize baseline labs; static already includes comorbidities + age(z) + sex
    bl_z = [((e["bval"][j] if e["bval"][j] is not None else scaler["lab"][l][0]) - scaler["lab"][l][0]) / scaler["lab"][l][1]
            for j, l in enumerate(CONF_LABS)]
    return np.array(bl_z + list(D.static_vec(e, scaler)), np.float32)


def smd(x_t, x_c):
    """standardized mean difference per covariate (|.|)."""
    sp = np.sqrt((x_t.var(0) + x_c.var(0)) / 2) + 1e-8
    return np.abs(x_t.mean(0) - x_c.mean(0)) / sp


def wsmd(x_t, x_c, w_t, w_c):
    """IPW-weighted SMD."""
    def wm(x, w): return (x * w[:, None]).sum(0) / w.sum()
    def wv(x, w, m): return (w[:, None] * (x - m) ** 2).sum(0) / w.sum()
    mt, mc = wm(x_t, w_t), wm(x_c, w_c)
    sp = np.sqrt((wv(x_t, w_t, mt) + wv(x_c, w_c, mc)) / 2) + 1e-8
    return np.abs(mt - mc) / sp


def main():
    tr, va, te, ch, ci, scaler, meta = D.build(seed=20260714)
    allx = tr + va + te                      # causal estimand is cohort-level; use everyone
    C = np.stack([confounders(e, scaler) for e in allx])
    T = np.array([1 if e["cohort"] == "dialysis" else 0 for e in allx])
    names = [f"base_{l.split()[0]}" for l in CONF_LABS] + COMORB + ["age", "sex"]
    print(f"n={len(allx)}  treated(dialysis)={T.sum()}  control(diuretic)={len(T)-T.sum()}")

    # ---- 1. propensity model P(T | C) ----
    ps_model = LogisticRegression(max_iter=1000, C=1.0)
    ps_model.fit(C, T)
    ps = ps_model.predict_proba(C)[:, 1].clip(1e-3, 1 - 1e-3)
    print(f"\npropensity model AUC = {roc_auc_score(T, ps):.3f}  "
          f"(high AUC = strong confounding-by-indication)")
    # top drivers of treatment assignment
    coef = sorted(zip(names, ps_model.coef_[0]), key=lambda x: -abs(x[1]))[:6]
    print("top assignment drivers:", ", ".join(f"{n}{'+' if c>0 else ''}{c:.2f}" for n, c in coef))

    # ---- 2. IPW + balance ----
    # stabilized weights
    pT = T.mean()
    w = np.where(T == 1, pT / ps, (1 - pT) / (1 - ps)).clip(0.1, 10)
    tmask, cmask = T == 1, T == 0
    before = smd(C[tmask], C[cmask])
    after = wsmd(C[tmask], C[cmask], w[tmask], w[cmask])
    print(f"\ncovariate balance (|SMD|, want <0.1):")
    print(f"  mean before {before.mean():.3f}  ->  after IPW {after.mean():.3f}")
    print(f"  max  before {before.max():.3f} ({names[before.argmax()]})  ->  after {after.max():.3f}")
    worst = sorted(zip(names, before, after), key=lambda x: -x[1])[:5]
    print("  worst confounders (name: before -> after):")
    for n, b, a in worst:
        print(f"    {n:16s} {b:.2f} -> {a:.2f}")

    # ---- 3. IPW / g-computation effect estimate (dialysis - diuretic) on post labs ----
    # outcome = last observed post value per lab (real units); IPW-weighted mean difference
    def last_post(e, j):
        s = sorted(e["post"].get(CONF_LABS[j], []))
        return s[-1][1] if s else None
    print(f"\ncausal effect estimate (dialysis - diuretic) on post labs:")
    print(f"  {'lab':20s} {'naive diff':>11} {'IPW-adjusted':>13}")
    for j, lab in enumerate(CONF_LABS):
        y = np.array([last_post(e, j) if last_post(e, j) is not None else np.nan for e in allx])
        ok = ~np.isnan(y)
        yt, yc = y[ok & tmask], y[ok & cmask]
        naive = yt.mean() - yc.mean()
        wt, wc = w[ok & tmask], w[ok & cmask]
        ipw = (yt * wt).sum() / wt.sum() - (yc * wc).sum() / wc.sum()
        print(f"  {lab:20s} {naive:+11.2f} {ipw:+13.2f}")
    print("\n(IPW-adjusted = the DAG/g-methods causal baseline to compare the world model against.)")


if __name__ == "__main__":
    main()
