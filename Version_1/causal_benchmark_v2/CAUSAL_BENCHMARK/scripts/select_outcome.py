"""
select_outcome.py  —  automated primary-outcome selection for Task C.

The spec requires the *system* to select the primary outcome Y from a candidate set,
rather than fixing it a priori. We score each derivable candidate outcome on the four
criteria from the spec and pick the highest-scoring one as primary (2nd as secondary):

  (a) completeness / low missingness across treatment groups
  (b) temporal alignment with PCI exposure (post-index measurement density)
  (c) clinical relevance to acute coronary intervention (fixed documented prior)
  (d) stability under propensity stratification (minimal imbalance-induced distortion)

Each criterion is mapped to [0,1]; the combined score is a documented weighted sum.
Output: data/outcome_selection.json (scorecard + selected primary/secondary).

NOTE: mortality / 14-day mortality / ICU-LOS from the spec are NOT derivable from the
MIMIC-IV cardiac-ext subset on disk (no admissions/patients/icustays tables), so the
candidate set is the lab-derived outcomes only. This is recorded in the output.
"""

import json
import logging
import numpy as np
from pathlib import Path

import taskC_common as tc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT = tc.BENCH / "data" / "outcome_selection.json"

# Documented criterion weights (sum to 1). Completeness is weighted highest because a
# differentially-missing outcome silently confounds the treatment contrast.
WEIGHTS = {"completeness": 0.35, "alignment": 0.20, "relevance": 0.25, "stability": 0.20}
N_STRATA = 5


def completeness(cohort, key):
    """(a) overall complete fraction × (1 − between-arm imbalance)."""
    pci = [e for e in cohort if tc.treatment_of(e) == 1]
    ctl = [e for e in cohort if tc.treatment_of(e) == 0]
    f_pci = np.mean([tc.outcome_present(e, key) for e in pci]) if pci else 0.0
    f_ctl = np.mean([tc.outcome_present(e, key) for e in ctl]) if ctl else 0.0
    overall = np.mean([tc.outcome_present(e, key) for e in cohort]) if cohort else 0.0
    imbalance = abs(f_pci - f_ctl)
    return {"score": float(overall * (1 - imbalance)),
            "complete_overall": round(float(overall), 3),
            "complete_pci": round(float(f_pci), 3),
            "complete_control": round(float(f_ctl), 3),
            "arm_imbalance": round(float(imbalance), 3)}


def alignment(cohort, key):
    """(b) mean post-index measurement density (saturating at 3 draws) over present episodes."""
    dens = []
    for e in cohort:
        o = e.get("outcomes", {}).get(key)
        if o and not o.get("missing", True):
            dens.append(min(o.get("n_post", 0), 3) / 3.0)
    return {"score": float(np.mean(dens)) if dens else 0.0,
            "mean_post_density_norm": round(float(np.mean(dens)), 3) if dens else 0.0,
            "n_present": len(dens)}


def stability(cohort, key, logit_by_id):
    """(d) 1 − SD of the per-propensity-stratum standardized treated−control difference.
    A stable outcome yields a consistent contrast across the propensity range; an outcome
    whose naive effect swings wildly with baseline risk is penalized."""
    vals, ts, lg = [], [], []
    for e in cohort:
        v = tc.outcome_value(e, key)
        if v is None or e["episode_id"] not in logit_by_id:
            continue
        vals.append(v); ts.append(tc.treatment_of(e)); lg.append(logit_by_id[e["episode_id"]])
    vals, ts, lg = np.array(vals, float), np.array(ts), np.array(lg, float)
    if len(vals) < 2 * N_STRATA or vals.std() == 0:
        return {"score": 0.0, "note": "insufficient_data", "n": int(len(vals))}
    z = (vals - vals.mean()) / vals.std()                      # standardized outcome
    edges = np.quantile(lg, np.linspace(0, 1, N_STRATA + 1))
    effects = []
    for i in range(N_STRATA):
        lo, hi = edges[i], edges[i + 1]
        m = (lg >= lo) & (lg <= hi if i == N_STRATA - 1 else lg < hi)
        zt, zc = z[m & (ts == 1)], z[m & (ts == 0)]
        if len(zt) >= 1 and len(zc) >= 1:
            effects.append(zt.mean() - zc.mean())
    if len(effects) < 2:
        return {"score": 0.0, "note": "too_few_strata", "n": int(len(vals))}
    sd = float(np.std(effects))
    return {"score": float(max(0.0, 1.0 - sd)), "strata_effect_sd": round(sd, 3),
            "n_strata_used": len(effects), "n": int(len(vals))}


def main():
    data, episodes = tc.load_episodes()
    cohort = tc.taskC_cohort(episodes)
    log.info(f"Task C cohort: {len(cohort)} episodes "
             f"(pci={sum(tc.treatment_of(e)==1 for e in cohort)}, "
             f"control={sum(tc.treatment_of(e)==0 for e in cohort)})")

    # Propensity (shared definition) for criterion (d).
    X, names, ids, T = tc.build_covariate_matrix(episodes)
    prop = tc.fit_propensity(X, T)
    logit_by_id = dict(zip(ids, prop["logit"]))
    log.info(f"Propensity AUC = {prop['auc']:.3f} (covariates d={X.shape[1]})")

    scorecard = {}
    for key in tc.CANDIDATE_OUTCOMES:
        a = completeness(cohort, key)
        b = alignment(cohort, key)
        c = {"score": tc.CLINICAL_RELEVANCE_PRIOR.get(key, 0.5)}
        d = stability(cohort, key, logit_by_id)
        combined = (WEIGHTS["completeness"] * a["score"] + WEIGHTS["alignment"] * b["score"]
                    + WEIGHTS["relevance"] * c["score"] + WEIGHTS["stability"] * d["score"])
        scorecard[key] = {"combined_score": round(float(combined), 4),
                          "completeness": a, "alignment": b,
                          "relevance": c, "stability": d}

    ranking = sorted(scorecard, key=lambda k: scorecard[k]["combined_score"], reverse=True)
    primary, secondary = ranking[0], (ranking[1] if len(ranking) > 1 else None)

    log.info("Outcome scorecard (combined | complete | align | relevance | stability):")
    for k in ranking:
        s = scorecard[k]
        log.info(f"  {k:24s} {s['combined_score']:.3f} | {s['completeness']['score']:.3f} | "
                 f"{s['alignment']['score']:.3f} | {s['relevance']['score']:.3f} | {s['stability']['score']:.3f}")
    log.info(f"SELECTED primary={primary}  secondary={secondary}")

    OUT.write_text(json.dumps({
        "task": "C_counterfactual_outcome_selection",
        "candidate_outcomes": tc.CANDIDATE_OUTCOMES,
        "excluded_outcomes_unavailable": [
            "in_hospital_mortality", "mortality_14d", "icu_length_of_stay"],
        "exclusion_reason": "MIMIC-IV core tables (admissions/patients/icustays) not on disk",
        "criterion_weights": WEIGHTS,
        "propensity_auc": round(prop["auc"], 4),
        "n_cohort": len(cohort),
        "ranking": ranking,
        "primary_outcome": primary,
        "secondary_outcome": secondary,
        "scorecard": scorecard,
    }, indent=2))
    log.info(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
