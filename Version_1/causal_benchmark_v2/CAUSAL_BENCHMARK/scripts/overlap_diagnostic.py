"""
overlap_diagnostic.py  —  does the 3-arm cohort actually OVERLAP? (positivity check)

A multi-arm counterfactual is only valid for patients who could plausibly receive ANY arm.
We estimate the generalized propensity score P(arm | covariates) with a multinomial model,
then report how many patients sit on COMMON SUPPORT (non-trivial probability of all 3 arms).
That common-support subgroup is the population the benchmark can honestly ask "what if" about.

Reads data/multiarm_cohort.json. Reports per-arm assignability (one-vs-rest AUC) and the
fraction of patients on common support at a probability floor TAU.
"""

import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

BENCH = Path(__file__).parent.parent
sys.path.insert(0, str(BENCH / "scripts"))
from build_dataset import COMORBIDITIES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

COHORT = BENCH / "data" / "multiarm_cohort.json"
OUT = BENCH / "data" / "overlap_diagnostic.json"
ARMS = ["pci", "cabg", "medical"]
TAU = float(os.environ.get("TASKC_SUPPORT_TAU", "0.10"))   # min per-arm prob to be "in play"


def covariates(eps):
    keys = sorted(COMORBIDITIES.keys())
    names = [f"comorbid_{k}" for k in keys] + ["n_comorbidities"]
    has_age = any(e.get("age") is not None for e in eps)
    if has_age:
        names += ["age"]
    X = []
    for e in eps:
        row = [float(e["comorbidities"][k]) for k in keys] + [float(e["n_comorbidities"])]
        if has_age:
            row.append(float(e["age"]) if e.get("age") is not None else np.nan)
        X.append(row)
    X = np.array(X, float)
    for j in range(X.shape[1]):                 # median-impute
        col = X[:, j]
        if np.any(np.isnan(col)):
            col[np.isnan(col)] = np.nanmedian(col) if not np.all(np.isnan(col)) else 0.0
            X[:, j] = col
    return X, names, has_age


def main():
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    data = json.loads(COHORT.read_text())
    eps = [e for e in data["episodes"] if e.get("eligible")]
    if not eps:
        eps = [e for e in data["episodes"] if e.get("_linked") is not False]
    y = np.array([ARMS.index(e["arm"]) for e in eps])
    X, names, has_age = covariates(eps)
    log.info(f"Overlap on {len(eps)} eligible patients; covariates={names} (age={'yes' if has_age else 'NOT YET'})")

    Xs = StandardScaler().fit_transform(X)
    clf = LogisticRegression(max_iter=3000, multi_class="multinomial", C=1.0).fit(Xs, y)
    P = clf.predict_proba(Xs)                    # (n, 3) generalized propensity

    # one-vs-rest assignability: how distinguishable is each arm (1.0 = trivially separable)
    aucs = {}
    for k, arm in enumerate(ARMS):
        yk = (y == k).astype(int)
        aucs[arm] = round(float(roc_auc_score(yk, P[:, k])), 3) if len(set(yk)) > 1 else None

    # common support: a patient is "in play for all arms" if min arm-prob >= TAU
    min_p = P.min(axis=1)
    on_support = min_p >= TAU
    by_arm = {arm: round(float(on_support[y == k].mean()), 3) for k, arm in enumerate(ARMS)}

    log.info(f"One-vs-rest assignability AUC (lower=more overlap): {aucs}")
    log.info(f"Common support @ TAU={TAU}: {on_support.mean():.3f} of patients in play for ALL 3 arms")
    log.info(f"  on-support fraction by arm: {by_arm}")
    log.info(f"  -> all-3 common-support cohort: {int(on_support.sum())} patients")

    # PAIRWISE overlap (the practical design): for each pair, binary propensity + the
    # standard overlap region (both treatment probs away from 0/1). Much larger than all-3.
    pairwise = {}
    log.info("Pairwise overlap (the usable contrasts):")
    for i in range(len(ARMS)):
        for j in range(i + 1, len(ARMS)):
            a, b = ARMS[i], ARMS[j]
            m = (y == i) | (y == j)
            yb = (y[m] == j).astype(int)         # prob of arm b
            if len(set(yb)) < 2:
                continue
            clf2 = LogisticRegression(max_iter=3000, C=1.0).fit(Xs[m], yb)
            p2 = clf2.predict_proba(Xs[m])[:, 1]
            auc2 = round(float(roc_auc_score(yb, p2)), 3)
            in_region = (p2 >= TAU) & (p2 <= 1 - TAU)
            pairwise[f"{a}_vs_{b}"] = {"n": int(m.sum()), "auc": auc2,
                                       "on_support_frac": round(float(in_region.mean()), 3),
                                       "n_on_support": int(in_region.sum())}
            log.info(f"  {a:8s} vs {b:8s}: n={int(m.sum()):4d}  AUC={auc2}  "
                     f"on-support={in_region.mean():.3f} ({int(in_region.sum())} patients)")

    OUT.write_text(json.dumps({
        "n_eligible": len(eps), "tau": TAU, "covariates": names, "age_available": has_age,
        "assignability_auc_ovr": aucs,
        "common_support_fraction": round(float(on_support.mean()), 3),
        "on_support_by_arm": by_arm,
        "n_on_common_support": int(on_support.sum()),
        "pairwise_overlap": pairwise,
        "note": "Run again once age/sex (patients.csv.gz) land — richer covariates sharpen overlap.",
    }, indent=2))
    log.info(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
