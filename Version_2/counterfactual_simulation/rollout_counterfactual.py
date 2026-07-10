"""rollout_counterfactual.py — the rich counterfactual output module.

Given a patient state z0 and a treatment plan (action sequence), roll the world model forward with
MONTE-CARLO sampling through the gaussian head (so every prediction carries an uncertainty band), and
decode to BOTH lab trajectories and OUTCOME-RISK trajectories. Compare treatment plans -> contrast.

Outputs per plan, per horizon step:
  labs:    {name: {mean, lo, hi}}  (real units, 10-90 percentile band from MC)
  outcome: {mortality/mortality_30d: {mean, lo, hi}}  (risk 0-1)
Plus a treatment-contrast summary (Δ risk vs factual) and a reliability flag.
"""
import json, pickle
from pathlib import Path
import numpy as np, pandas as pd, torch
from train_substrate_wm import ACJEPA, LabDecoder, CORE, LOINCS, LABN, NL, ARM
from add_outcome_decoder import OutcomeDecoder, OUTC

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
DEV = "cuda" if torch.cuda.is_available() else "cpu"
K = 64        # MC samples
ARMN = {v: k for k, v in ARM.items()}


def load():
    ck = torch.load(BASE/"data/world_model_enriched.pt", map_location=DEV)
    m = ACJEPA(ck["zdim"], ck["adim"]).to(DEV); m.load_state_dict(ck["model"]); m.eval()
    ld = LabDecoder(ck["zdim"], NL).to(DEV); ld.load_state_dict(ck["dec"]); ld.eval()
    od = OutcomeDecoder(ck["zdim"], len(OUTC)).to(DEV); od.load_state_dict(ck["outcome_dec"]); od.eval()
    mean = np.array(ck["lab_scaler_mean"]); std = np.sqrt(np.array(ck["lab_scaler_var"]))
    return m, ld, od, mean, std, ck


@torch.no_grad()
def mc_rollout(model, ld, od, mean, std, z0, action_seq, dts):
    """z0:[768]. action_seq:[H,adim]. dts:[H]. Returns per-step lab & outcome bands (MC over K)."""
    z = torch.tensor(z0, device=DEV).float().repeat(K, 1)     # [K,768]
    steps = []
    for h in range(len(action_seq)):
        a = torch.tensor(action_seq[h], device=DEV).float().repeat(K, 1)
        dt = torch.tensor([dts[h]], device=DEV).float().repeat(K)
        _, t = model._core(z, a, dt)
        mu, lv = model.mu(t), model.logvar(t).clamp(-8, 8)
        z = z + mu + torch.randn_like(mu) * (0.5 * lv).exp()   # sample next latent
        labs = ld(z).cpu().numpy() * std + mean                # [K,NL] real units
        risk = torch.sigmoid(od(z)).cpu().numpy()              # [K,len(OUTC)]
        steps.append((labs, risk))
    return steps


def band(x):   # x:[K]
    return {"mean": round(float(np.mean(x)), 2),
            "lo": round(float(np.percentile(x, 10)), 2),
            "hi": round(float(np.percentile(x, 90)), 2)}


def summarize(steps, labs_show):
    labtraj, outtraj = [], []
    for labs, risk in steps:
        labtraj.append({nm: band(labs[:, LABN.index(nm)]) for nm in labs_show})
        outtraj.append({OUTC[i]: band(risk[:, i]) for i in range(len(OUTC))})
    return labtraj, outtraj


def main():
    model, ld, od, mean, std, ck = load()
    sub = pickle.load(open(BASE/"data/train_substrate.pkl","rb"))
    sp = json.loads((BASE/"data/splits.json").read_text()); test = set(sp["splits"]["test"])
    LABS_SHOW = ["creatinine", "bun", "potassium", "lactate" if "lactate" in LABN else "sodium"]

    # pick a test patient with an abnormal baseline (where the sim is reliable) + enough horizon
    chosen = None
    for e in sub:
        if int(e["patient_id"]) not in test: continue
        if e["s"].shape[0] >= 6 and float(np.abs(e["action_matrix"][1:6]).sum()) > 0:
            chosen = e; break
    e = chosen
    H = min(5, e["s"].shape[0]-1)
    z0 = e["s"][0]; hrs = np.asarray(e["hours"], float)
    dts = [max(hrs[i+1]-hrs[i], 0.0) for i in range(H)]
    factual = e["action_matrix"][1:H+1]
    no_treat = np.zeros_like(factual)

    plans = {"factual (real treatment)": factual, "counterfactual: no treatment": no_treat}
    out = {"patient_id": int(e["patient_id"]), "arm": ARMN.get(ARM.get(str(e["outcomes"].get("arm")),0)),
           "horizon_steps": H, "MC_samples": K, "delta_t_hours": [round(x,1) for x in dts],
           "actual_outcome": {k: int(e["outcomes"].get(k,0) or 0) for k in OUTC},
           "plans": {}}
    for name, seq in plans.items():
        steps = mc_rollout(model, ld, od, mean, std, z0, seq, dts)
        labtraj, outtraj = summarize(steps, LABS_SHOW)
        out["plans"][name] = {"lab_trajectory": labtraj, "outcome_risk_trajectory": outtraj,
                              "final_mortality_risk": outtraj[-1]["mortality"]}
    # contrast
    f = out["plans"]["factual (real treatment)"]["final_mortality_risk"]["mean"]
    n = out["plans"]["counterfactual: no treatment"]["final_mortality_risk"]["mean"]
    out["treatment_contrast"] = {"final_mortality_factual": f, "final_mortality_no_treatment": n,
                                 "delta (treatment effect on mortality risk)": round(f - n, 3)}
    # reliability flag: is the baseline abnormal for the shown labs?
    z0lab = (ld(torch.tensor(z0, device=DEV).float()[None]).detach().cpu().numpy()*std+mean)[0]
    refs = {"creatinine": (0.5,1.2), "bun": (6,20), "potassium": (3.3,5.1), "sodium": (133,145)}
    abn = [nm for nm in LABS_SHOW if nm in refs and not (refs[nm][0] <= z0lab[LABN.index(nm)] <= refs[nm][1])]
    out["reliability"] = {"abnormal_baseline_labs": abn,
        "flag": "RELIABLE (dynamic case — sim beats persistence here)" if abn
                else "LOW-CONFIDENCE (stable-normal — persistence as good)"}

    (BASE/"data/rollout_example.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: out[k] for k in ["patient_id","arm","actual_outcome",
          "treatment_contrast","reliability"]}, indent=2))
    print("\nfactual outcome-risk trajectory (mortality):")
    for i, s in enumerate(out["plans"]["factual (real treatment)"]["outcome_risk_trajectory"]):
        print(f"  step{i+1}: {s['mortality']}")
    print(f"\nfull rich output -> data/rollout_example.json")


if __name__ == "__main__":
    main()
