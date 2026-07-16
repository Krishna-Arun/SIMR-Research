#!/usr/bin/env python3
"""
Matched-pair validation of the world model -- the rigorous counterfactual test.

Per-patient discrimination can cheat via confounding: sicker-kidney patients get
dialysis, so the model might use STATE cues (not the intervention's effect) to tell
the arms apart. Matching neutralizes that: pair two SIMILAR patients (one dialysis,
one diuretic) so their states are balanced, then ask whether the model still recovers
the effect. If it does, that's evidence of a causal effect, not confounding.

All matching is done WITHIN the held-out test split (patients the WM never trained on).

Reports:
  1. covariate balance (SMD) before vs after matching -- confirms confounders neutralized
  2. matched-pair DISCRIMINATION: assign the two observed post-states to arms; chance 50%
  3. EFFECT RECOVERY per lab: model's predicted dialysis-vs-diuretic effect vs the
     observed matched-pair difference (V5-style "gate"): mean effect, sign agreement, corr
"""
import json, os
import numpy as np
import torch
import wm_data as D
from wm_model import WorldModel

HERE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(HERE, "wm_checkpoint.pt")


def confounders(e, sc):
    """baseline lab values (4) + age_z + sex + comorbidity flags (10)."""
    v = [(e["bval"][j] if e["bval"][j] is not None else 0.0) for j in range(len(D.TARGET_LABS))]
    return v + D.static_vec(e, sc)


def smd(a, b):
    a, b = np.asarray(a), np.asarray(b)
    sp = np.sqrt((a.var(0) + b.var(0)) / 2) + 1e-8
    return np.abs(a.mean(0) - b.mean(0)) / sp


def main():
    ckpt = torch.load(CKPT, map_location="cpu")
    channels, scaler, meta, targs = ckpt["channels"], ckpt["scaler"], ckpt["meta"], ckpt["args"]
    ci = {tuple(c): i for i, c in enumerate(channels)}
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = WorldModel(meta["C"], meta["n_static"], n_labs=meta["n_labs"],
                       action_dim=meta["action_dim"], d=targs["d"], H=meta["H"]).to(device)
    model.load_state_dict(ckpt["model"]); model.eval()

    train, val, test, ch, ci2, sc, meta2 = D.build(seed=targs["seed"])
    dial = [e for e in test if e["cohort"] == "dialysis"]
    diur = [e for e in test if e["cohort"] == "diuretic"]
    print(f"test patients: {len(dial)} dialysis, {len(diur)} diuretic")

    # ---- confounders (standardized over all test patients) ----
    allc = np.array([confounders(e, sc) for e in test], dtype=float)
    mu, sd = allc.mean(0), allc.std(0) + 1e-8
    def cz(e): return (np.array(confounders(e, sc)) - mu) / sd
    Cd = np.array([cz(e) for e in dial]); Cu = np.array([cz(e) for e in diur])

    # ---- greedy 1:1 nearest-neighbor matching (dialysis -> diuretic), with caliper ----
    dists = np.linalg.norm(Cd[:, None, :] - Cu[None, :, :], axis=2)  # [nd, nu]
    nn = dists.min(1)
    caliper = float(np.quantile(nn, 0.80))                           # keep best-matched ~80%
    used = set(); pairs = []
    for i in np.argsort(nn):                                         # match closest-first
        cand = [(dists[i, k], k) for k in range(len(diur)) if k not in used]
        if not cand:
            break
        dmin, j = min(cand)
        if dmin <= caliper:
            used.add(j); pairs.append((int(i), j))
    print(f"matched pairs (caliper {caliper:.2f}): {len(pairs)}")
    if not pairs:
        print("no pairs matched"); return

    # balance before/after
    before = smd(Cd, Cu)
    mi = [i for i, _ in pairs]; mj = [j for _, j in pairs]
    after = smd(Cd[mi], Cu[mj])
    print(f"mean |SMD| all covariates:  before {before.mean():.3f}  ->  after matching {after.mean():.3f}")
    print(f"max  |SMD|:                  before {before.max():.3f}   ->  after {after.max():.3f}")

    # ---- WM predictions under canonical dialysis / diuretic actions ----
    import statistics as st
    dur = st.median([e["action"][2] for e in train if e["cohort"] == "dialysis"] or [1.0])
    ratio = st.median([e["action"][3] for e in train if e["cohort"] == "diuretic"] or [0.5])
    a_dial = torch.tensor([1.0, 0.0, dur, 0.0]); a_diur = torch.tensor([0.0, 1.0, 0.0, ratio])
    labsd = [scaler["lab"][l] for l in D.TARGET_LABS]                # (mean, sd) per lab

    @torch.no_grad()
    def preds(e):
        g, a = D.featurize(e, channels, ci, scaler)
        grid = torch.tensor(g).unsqueeze(0).to(device)
        act = torch.tensor(a).unsqueeze(0).to(device)
        stat = torch.tensor(D.static_vec(e, sc)).float().unsqueeze(0).to(device)
        pd = model(grid, act, stat, a_dial.unsqueeze(0).to(device))[0].cpu().numpy()
        pu = model(grid, act, stat, a_diur.unsqueeze(0).to(device))[0].cpu().numpy()
        return pd, pu

    def unz(vec):  # standardized -> real per lab
        return np.array([labsd[k][0] + vec[k] * labsd[k][1] for k in range(4)])
    def z(vec):    # real -> standardized per lab
        return np.array([(vec[k] - labsd[k][0]) / labsd[k][1] for k in range(4)])

    disc_correct = 0
    dobs = []; dpred = []
    for i, j in pairs:
        ed, eu = dial[i], diur[j]
        pd_d, pu_d = preds(ed)     # dialysis patient's state: pred under dial / diur (standardized)
        pd_u, pu_u = preds(eu)     # diuretic patient's state
        y_d = z(ed["targets"]); y_u = z(eu["targets"])                    # observed posts (standardized)
        pd = (pd_d + pd_u) / 2; pu = (pu_d + pu_u) / 2                    # arm predictions (matched state avg)
        # discrimination: assign observed posts to arms
        correct = np.sum((pd - y_d) ** 2) + np.sum((pu - y_u) ** 2)
        swap = np.sum((pd - y_u) ** 2) + np.sum((pu - y_d) ** 2)
        disc_correct += (correct < swap)
        # effect recovery (real units)
        dpred.append(unz(pd) - unz(pu))
        dobs.append(np.array(ed["targets"]) - np.array(eu["targets"]))
    dobs = np.array(dobs); dpred = np.array(dpred)

    print(f"\nMATCHED-PAIR DISCRIMINATION: {disc_correct/len(pairs):.3f}  (chance 0.500, n={len(pairs)})")
    print("\nEFFECT RECOVERY (dialysis - diuretic), per lab:")
    print(f"  {'lab':20s} {'obs_effect':>11} {'pred_effect':>12} {'sign_agree':>11} {'pearson_r':>10}")
    for k, lab in enumerate(D.TARGET_LABS):
        o, p = dobs[:, k], dpred[:, k]
        sign = np.mean(np.sign(o) == np.sign(p))
        r = np.corrcoef(o, p)[0, 1] if o.std() > 0 and p.std() > 0 else float("nan")
        print(f"  {lab:20s} {o.mean():11.3f} {p.mean():12.3f} {sign:11.3f} {r:10.3f}")
    json.dump({"n_pairs": len(pairs), "discrimination": disc_correct / len(pairs),
               "smd_before": float(before.mean()), "smd_after": float(after.mean())},
              open(os.path.join(HERE, "wm_matched_validation.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
