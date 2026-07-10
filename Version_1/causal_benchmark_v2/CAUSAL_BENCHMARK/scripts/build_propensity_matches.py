"""
build_propensity_matches.py  —  Task C counterfactual-pair construction.

For each patient we find nearest neighbors of the OPPOSITE treatment using a combined
distance over (1) a learned pre-treatment embedding and (2) propensity-score similarity,
restricted to a propensity caliper to guarantee overlap. Matching is BIDIRECTIONAL:
  - each PCI (treated) episode -> K control neighbors      => proxy Y(0)
  - each control episode       -> K PCI neighbors          => proxy Y(1)
The matched neighbors' observed outcomes give the proxy counterfactual label, and hence
a proxy individual treatment effect (ITE = Y(1) - Y(0)) used as the PEHE reference.

For every tracked outcome we record both the numeric value AND the rising/falling/stable
direction (factual = observed; counterfactual = derived from the proxy vs the patient's
own pre-index baseline).

Output: data/taskC_matched.json  (per-episode proxy labels + directed pairs + balance/overlap).

NOTE: validity rests on no-unmeasured-confounding given the available covariates. Age/sex
are absent from this dataset; labs/ICD/comorbidities only partially proxy them. The Sodium
negative control (scored downstream) and the post-match SMD here are the residual-confounding
diagnostics.
"""

import json
import logging
import os
import numpy as np
from pathlib import Path

import taskC_common as tc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUT = tc.BENCH / "data" / "taskC_matched.json"
SEL = tc.BENCH / "data" / "outcome_selection.json"

K = int(os.environ.get("TASKC_K", "3"))
CALIPER_SD = float(os.environ.get("TASKC_CALIPER", "0.2"))   # caliper = CALIPER_SD × SD(logit propensity)
LAMBDA_PS = float(os.environ.get("TASKC_LAMBDA_PS", "1.0"))  # weight on propensity term in the distance
EMBED_DIM = int(os.environ.get("TASKC_EMBED_DIM", "8"))


def _autoencoder(Xs, dim, seed=0):
    """Tiny MLP autoencoder -> bottleneck embedding (optional; TASKC_EMBED=ae)."""
    import torch
    torch.manual_seed(seed)
    n, d = Xs.shape
    dim = min(dim, d)
    X = torch.tensor(Xs, dtype=torch.float32)
    enc = torch.nn.Sequential(torch.nn.Linear(d, max(2 * dim, 8)), torch.nn.ReLU(),
                              torch.nn.Linear(max(2 * dim, 8), dim))
    dec = torch.nn.Sequential(torch.nn.Linear(dim, max(2 * dim, 8)), torch.nn.ReLU(),
                              torch.nn.Linear(max(2 * dim, 8), d))
    opt = torch.optim.Adam(list(enc.parameters()) + list(dec.parameters()), lr=1e-2)
    for _ in range(300):
        opt.zero_grad()
        z = enc(X)
        loss = torch.nn.functional.mse_loss(dec(z), X)
        loss.backward(); opt.step()
    with torch.no_grad():
        return enc(X).numpy()


def learn_embedding(Xs):
    """Learned pre-treatment embedding. Default: PCA-whitened (Euclidean ≈ Mahalanobis),
    a principled unsupervised representation. Optional torch autoencoder via TASKC_EMBED=ae."""
    mode = os.environ.get("TASKC_EMBED", "pca")
    if mode == "ae":
        try:
            return _autoencoder(Xs, EMBED_DIM), "autoencoder"
        except Exception as e:
            log.warning(f"autoencoder unavailable ({e}); falling back to PCA")
    from sklearn.decomposition import PCA
    d = min(EMBED_DIM, Xs.shape[1])
    z = PCA(n_components=d, whiten=True, random_state=0).fit_transform(Xs)
    return z, f"pca_whiten_{d}"


def main():
    primary, secondary = tc.PRIMARY_OUTCOME_DEFAULT, "delta_creatinine_72h"
    if SEL.exists():
        sel = json.loads(SEL.read_text())
        primary = sel.get("primary_outcome", primary)
        secondary = sel.get("secondary_outcome", secondary)
    tracked = [o for o in dict.fromkeys([primary, secondary] + tc.CANDIDATE_OUTCOMES) if o]
    log.info(f"Tracked outcomes (proxy + direction): primary={primary}, secondary={secondary}")

    data, episodes = tc.load_episodes()
    X, names, ids, T = tc.build_covariate_matrix(episodes)
    ep_by_id = {e["episode_id"]: e for e in episodes}
    prop = tc.fit_propensity(X, T)
    logit, Xs = prop["logit"], prop["Xs"]
    z, embed_name = learn_embedding(Xs)
    sd_logit = float(logit.std()) or 1.0
    caliper = CALIPER_SD * sd_logit
    log.info(f"Propensity AUC={prop['auc']:.3f}; embedding={embed_name}; "
             f"caliper={caliper:.4f} ({CALIPER_SD}×SD logit)")

    treated_idx = np.where(T == 1)[0]
    control_idx = np.where(T == 0)[0]

    def neighbors(i, pool):
        cand = []
        for j in pool:
            if j == i:
                continue                      # exclude self (matters for same-arm validation)
            dl = abs(logit[i] - logit[j])
            if dl > caliper:
                continue
            dist = float(np.linalg.norm(z[i] - z[j]) + LAMBDA_PS * (dl / sd_logit))
            cand.append((dist, int(j), float(dl)))
        cand.sort(key=lambda x: x[0])
        return cand[:K]

    def neighbor_mean(ep_idx_list, key):
        vals = [tc.outcome_value(ep_by_id[ids[j]], key) for j in ep_idx_list]
        vals = [v for v in vals if v is not None]
        return (float(np.mean(vals)), len(vals)) if vals else (None, 0)

    records, pairs = [], []
    matched_mask = np.zeros(len(T), bool)
    n_unmatched = {"pci": 0, "control": 0}

    for i in range(len(T)):
        arm = "pci" if T[i] == 1 else "control"
        opp_pool = control_idx if T[i] == 1 else treated_idx
        same_pool = treated_idx if T[i] == 1 else control_idx
        nbrs = neighbors(i, opp_pool)                 # opposite-arm => counterfactual proxy
        same_nbrs = neighbors(i, same_pool)           # same-arm => factual-validation estimate
        ep = ep_by_id[ids[i]]
        rec = {"episode_id": ids[i], "treatment": int(T[i]), "arm": arm,
               "propensity": round(float(prop["propensity"][i]), 4),
               "n_matches": len(nbrs), "match_ids": [ids[j] for _, j, _ in nbrs],
               "outcomes": {}}
        if not nbrs:
            n_unmatched[arm] += 1
        else:
            matched_mask[i] = True
            for _, j, _ in nbrs:
                matched_mask[j] = True
        base_by_key = {k: tc.marker_baseline(ep, k) for k in tracked}
        for key in tracked:
            factual = tc.outcome_value(ep, key)
            proxy, n_proxy = neighbor_mean([j for _, j, _ in nbrs], key)
            # Factual-validation: estimate THIS episode's own (factual-treatment) outcome from
            # same-arm neighbors. Comparing to the observed factual quantifies matcher trust.
            fac_est, n_fac = neighbor_mean([j for _, j, _ in same_nbrs], key)
            # ITE = Y(1) - Y(0); treated observe Y(1), control observe Y(0)
            ite = None
            if factual is not None and proxy is not None:
                ite = (factual - proxy) if T[i] == 1 else (proxy - factual)
            rec["outcomes"][key] = {
                "factual": round(factual, 4) if factual is not None else None,
                "counterfactual_proxy": round(proxy, 4) if proxy is not None else None,
                "n_proxy": n_proxy,
                "ite_proxy": round(ite, 4) if ite is not None else None,
                "factual_estimate_same_arm": round(fac_est, 4) if fac_est is not None else None,
                "n_factual_proxy": n_fac,
                "factual_direction": tc.direction_from_value(factual, key, base_by_key[key]),
                "counterfactual_direction_proxy": tc.direction_from_value(proxy, key, base_by_key[key]),
            }
        records.append(rec)

        # Directed pairs (treated -> control) for transparency / pairwise scoring.
        if T[i] == 1:
            for dist, j, dl in nbrs:
                pairs.append({
                    "pair_id": f"tc_pair_{len(pairs):06d}",
                    "treated_id": ids[i], "control_id": ids[j],
                    "match_quality": {
                        "combined_distance": round(dist, 4),
                        "propensity_gap": round(dl, 4),
                        "comorbidity_distance": int(sum(
                            1 for kk in ep["comorbidities"]
                            if ep["comorbidities"][kk] != ep_by_id[ids[j]]["comorbidities"].get(kk, 0))),
                        "embedding_distance": round(float(np.linalg.norm(z[i] - z[j])), 4),
                    }})

    balance_pre = tc.balance_report(X, T, names, mask=None)
    # Proper matched-sample balance: SMD between the treated and control SIDES of the actual
    # treated->control pairs (with multiplicity), not a loose unique-episode mask.
    idx_of = {ids[i]: i for i in range(len(ids))}
    mt = [idx_of[p["treated_id"]] for p in pairs]
    mc = [idx_of[p["control_id"]] for p in pairs]
    if mt:
        per = {nm: round(tc.smd(X[mt, j], X[mc, j]), 4) for j, nm in enumerate(names)}
        vals = [v for v in per.values() if v == v]
        worst = max(per, key=lambda k: per[k]) if per else None
        balance_post = {"per_feature": per, "n_pairs": len(pairs),
                        "mean_abs_smd": round(float(np.mean(vals)), 4) if vals else None,
                        "max_abs_smd": round(float(np.max(vals)), 4) if vals else None,
                        "worst_feature": worst}
    else:
        balance_post = {"per_feature": {}, "n_pairs": 0}
    overlap = {
        "propensity_pci": [round(float(prop["propensity"][treated_idx].min()), 4),
                           round(float(prop["propensity"][treated_idx].max()), 4)],
        "propensity_control": [round(float(prop["propensity"][control_idx].min()), 4),
                               round(float(prop["propensity"][control_idx].max()), 4)],
        "frac_pci_matched": round(float(matched_mask[treated_idx].mean()), 3),
        "frac_control_matched": round(float(matched_mask[control_idx].mean()), 3),
    }
    log.info(f"Pairs (treated→control): {len(pairs)}; "
             f"unmatched pci={n_unmatched['pci']} control={n_unmatched['control']}")
    log.info(f"Balance mean|SMD|: pre={balance_pre['mean_abs_smd']} -> post={balance_post['mean_abs_smd']} "
             f"(max post={balance_post['max_abs_smd']}; target <0.1)")

    OUT.write_text(json.dumps({
        "task": "C_counterfactual_matched_pairs",
        "primary_outcome": primary, "secondary_outcome": secondary,
        "tracked_outcomes": tracked,
        "matching": {"k": K, "caliper_sd": CALIPER_SD, "caliper": round(caliper, 4),
                     "lambda_ps": LAMBDA_PS, "embedding": embed_name, "with_replacement": True,
                     "distance": "‖embed_t−embed_c‖ + lambda_ps·|Δlogit|/SD(logit), within caliper"},
        "propensity_auc": round(prop["auc"], 4),
        "covariate_features": names,
        "n_pairs": len(pairs),
        "n_unmatched": n_unmatched,
        "overlap": overlap,
        "balance": {"pre_match": balance_pre, "post_match": balance_post},
        "episodes": records,
        "pairs": pairs,
    }, indent=2))
    log.info(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
