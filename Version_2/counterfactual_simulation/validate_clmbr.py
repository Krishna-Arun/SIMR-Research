"""
validate_clmbr.py — the validation gate: is the frozen CLMBR embedding actually good enough to
build an action-conditioned world model on? Three cheap checks before committing to Layer 2/3.

  1. Collapse check   — do embeddings have real spread (variance, effective rank)? A collapsed
                        encoder makes JEPA prediction trivial-but-useless.
  2. Outcome probe    — linear probe from a patient's embedding -> mortality / readmission (AUROC).
                        If z_t carries clinical state, these beat 0.5 clearly. (EHRSHOT-style.)
  3. Arm separation   — can a linear probe recover the treatment arm from the embedding? (sanity +
                        a confounding read: strong separation = arms live in different regions.)

Reads encoded_states_clmbr.pkl (list of {patient_id, s:[T,768], action_ids, hours, outcomes}).
Run in the simr env (sklearn/numpy/pandas) — no femr needed.
"""
from __future__ import annotations

import pickle
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

PKL = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/data/encoded_states_clmbr.pkl")


def main():
    data = pickle.load(open(PKL, "rb"))
    print(f"loaded {len(data)} patients")
    T = [d["s"].shape[0] for d in data]
    dim = data[0]["s"].shape[1]
    print(f"embedding dim={dim}; timepoints/patient: min={min(T)} median={int(np.median(T))} max={max(T)} total={sum(T):,}")

    # patient-level feature = mean-pooled embedding + last embedding (concatenated)
    Xmean = np.stack([d["s"].mean(0) for d in data])
    Xlast = np.stack([d["s"][-1] for d in data])
    X = np.concatenate([Xmean, Xlast], axis=1)

    # ---- 1. collapse check ----
    allz = np.concatenate([d["s"] for d in data], axis=0)
    per_dim_std = allz.std(0)
    # effective rank via singular-value entropy
    zc = allz - allz.mean(0)
    sv = np.linalg.svd(zc[:20000] if len(zc) > 20000 else zc, compute_uv=False)
    p = sv / sv.sum()
    eff_rank = float(np.exp(-(p * np.log(p + 1e-12)).sum()))
    print("\n[1] COLLAPSE CHECK")
    print(f"    per-dim std: mean={per_dim_std.mean():.4f} min={per_dim_std.min():.4f} "
          f"(#near-zero<1e-4: {(per_dim_std<1e-4).sum()}/{dim})")
    print(f"    effective rank ≈ {eff_rank:.1f} / {dim}   "
          f"({'OK — not collapsed' if eff_rank > 20 else 'WARNING — low, possible collapse'})")

    # ---- 2. outcome probes ----
    def probe(y, name):
        y = np.asarray(y)
        if len(np.unique(y)) < 2 or y.sum() < 10 or (len(y) - y.sum()) < 10:
            print(f"    {name:16s}: skipped (only {int(y.sum())}/{len(y)} positive)")
            return
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))
        cv = StratifiedKFold(5, shuffle=True, random_state=0)
        auc = cross_val_score(clf, X, y, cv=cv, scoring="roc_auc")
        print(f"    {name:16s}: AUROC {auc.mean():.3f} ± {auc.std():.3f}   (prevalence {y.mean():.2f})")

    print("\n[2] OUTCOME PROBES (5-fold CV AUROC from patient embedding)")
    probe([d["outcomes"].get("mortality_30d", 0) for d in data], "mortality_30d")
    probe([d["outcomes"].get("mortality", 0) for d in data], "in_hosp_mortality")
    probe([d["outcomes"].get("readmission_30d", 0) for d in data], "readmission_30d")

    # ---- 3. arm separation ----
    print("\n[3] ARM SEPARATION (one-vs-rest AUROC)")
    arms = np.array([d["outcomes"].get("arm", "?") for d in data])
    for a in ["pci", "cabg", "medical"]:
        probe((arms == a).astype(int), f"arm={a}")

    print("\nGATE READ: pass if not collapsed AND mortality/readmission AUROC clearly > 0.5 "
          "(≈0.7+ means CLMBR encodes real clinical state — safe to build the world model on).")


if __name__ == "__main__":
    main()
