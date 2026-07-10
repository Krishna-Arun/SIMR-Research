"""rollout_api.py — importable engine + candidate-plan enumeration for the LLM-coupling ablation.

Wraps the (script-only) rollout_counterfactual module into a clean library:
  engine = load_engine()                                  # load WM + decoders + action schema, once
  plans  = enumerate_candidate_plans(e, engine.schema)    # {name: action_seq[H,34]}, deterministic
  out    = rollout_patient(engine, z0, plans, dts)        # rich per-plan lab/outcome bands + contrast

`out` matches the structure of data/rollout_example.json (see rollout_counterfactual.main), so it can be
serialized to a text SIMULATOR-EVIDENCE block (Route A) or its latents packed for injection (Route B).

The world model is used ONLY as an INPUT/evidence channel. It is never a label source (see plan §Data).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
# the reused modules live in BASE and import each other by top-level name, so BASE must be on sys.path
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import torch  # noqa: E402
from rollout_counterfactual import load, mc_rollout, band, summarize, K, ARMN  # noqa: E402,F401
from train_substrate_wm import LABN, NL, ARM  # noqa: E402
from add_outcome_decoder import OUTC  # noqa: E402

DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Reference ranges for the reliability flag (a baseline OUTSIDE the range = "dynamic case", where the
# world model beats persistence; see eval_simulator_benchmarkB + SYSTEM_OVERVIEW §5).
REFS = {
    "creatinine": (0.5, 1.2), "bun": (6, 20), "potassium": (3.3, 5.1), "sodium": (133, 145),
    "chloride": (98, 107), "bicarbonate": (22, 29), "glucose": (70, 140), "magnesium": (1.6, 2.6),
    "phosphate": (2.5, 4.5), "hemoglobin": (12, 17), "hematocrit": (36, 50), "platelets": (150, 400),
    "wbc": (4, 11), "anion_gap": (4, 12),
}
DEFAULT_LABS_SHOW = ["creatinine", "bun", "potassium", "sodium", "glucose", "hemoglobin"]


@dataclass
class Engine:
    model: object
    ld: object
    od: object
    mean: np.ndarray
    std: np.ndarray
    ck: dict
    schema: dict


def load_engine() -> Engine:
    m, ld, od, mean, std, ck = load()
    schema = json.loads((BASE / "data/action_schema.json").read_text())
    return Engine(model=m, ld=ld, od=od, mean=mean, std=std, ck=ck, schema=schema)


def _col_idx(schema: dict) -> dict:
    return {c: i for i, c in enumerate(schema["columns"])}


def enumerate_candidate_plans(e: dict, schema: dict, horizon: int = 5,
                              max_plans: int = 6) -> "dict[str, np.ndarray]":
    """Deterministic menu of length-H action sequences for one substrate entry `e`.

    Always includes: factual, no_treatment, alt_arm (revascularization flip). Then adds toggles on the
    dominant continuous drip the patient actually received, until max_plans is reached. Pure function of
    the patient's factual actions + schema, so it is IDENTICAL across all ablation arms.
    """
    cidx = _col_idx(schema)
    T = int(e["s"].shape[0])
    H = min(horizon, T - 1)
    if H < 1:
        raise ValueError(f"patient {e.get('patient_id')} has too few timepoints (T={T})")
    A = np.asarray(e["action_matrix"], dtype=np.float32)
    factual = A[1:H + 1].copy()

    plans: "dict[str, np.ndarray]" = {}
    plans["factual"] = factual
    plans["no_treatment"] = np.zeros_like(factual)

    arm = str(e["outcomes"].get("arm", "medical"))
    pci_c, cabg_c = cidx["pci__on"], cidx["cabg__on"]
    alt = factual.copy()
    if arm == "medical":
        alt[:, pci_c] = 1.0  # counterfactual: what if this medical patient had received PCI
        plans["alt_arm_pci"] = alt
    else:
        alt[:, pci_c] = 0.0
        alt[:, cabg_c] = 0.0  # counterfactual: what if revascularization had been withheld
        plans["alt_arm_medical"] = alt

    # dominant-drip toggles: rank continuous drips by how active they were in the factual window
    cont = list(schema.get("cont_groups", {}).keys())
    activity = []
    for g in cont:
        on_c = cidx.get(f"{g}__on")
        if on_c is None:
            continue
        activity.append((float(factual[:, on_c].sum()), g))
    activity.sort(reverse=True)
    for _, g in activity:
        if len(plans) >= max_plans:
            break
        on_c = cidx[f"{g}__on"]
        rate_c = cidx.get(f"{g}__rate")
        present = factual[:, on_c].sum() > 0
        tog = factual.copy()
        if present:  # remove it: what if we withheld this drip
            tog[:, on_c] = 0.0
            if rate_c is not None:
                tog[:, rate_c] = 0.0
            plans[f"remove_{g}"] = tog
        else:  # add it at a typical (median => normalized 0) dose
            tog[:, on_c] = 1.0
            if rate_c is not None:
                tog[:, rate_c] = 0.0
            plans[f"add_{g}"] = tog

    return plans


@torch.no_grad()
def mc_rollout_latents(engine: Engine, z0: np.ndarray, action_seq, dts) -> np.ndarray:
    """Like mc_rollout but returns the ENDPOINT latent samples [K, 768] (not decoded), so the latent-
    injection projector can consume the raw world-model state distribution. Same sampling as
    rollout_counterfactual.mc_rollout (gaussian residual head)."""
    m = engine.model
    z = torch.tensor(z0, device=DEV).float().repeat(K, 1)
    for h in range(len(action_seq)):
        a = torch.tensor(np.asarray(action_seq[h], dtype=np.float32), device=DEV).float().repeat(K, 1)
        dt = torch.tensor([float(dts[h])], device=DEV).float().repeat(K)
        _, t = m._core(z, a, dt)
        mu, lv = m.mu(t), m.logvar(t).clamp(-8, 8)
        z = z + mu + torch.randn_like(mu) * (0.5 * lv).exp()
    return z.cpu().numpy()  # [K, 768]


def build_latent_pack(engine: Engine, e: dict, tz_index: int = 0, horizon: int = 3,
                      hist: int = 3, plans: Optional["dict[str, np.ndarray]"] = None) -> dict:
    """Assemble the raw-latent 'sentence' for embedding injection:
        z_now      : factual latent at tz_index                                 [768]
        z_hist     : up to `hist` preceding factual latents (oldest->newest)     [<=hist, 768]
        cf         : {plan_name: [mean(768) ++ std(768)]} endpoint distributions
    Deterministic given the substrate entry + enumerated plans."""
    s = np.asarray(e["s"], dtype=np.float32)
    T = s.shape[0]
    i = min(tz_index, T - 2)
    H = min(horizon, T - 1 - i)
    z_now = s[i]
    lo = max(0, i - hist)
    z_hist = s[lo:i]  # [<=hist, 768]
    hrs = np.asarray(e["hours"], dtype=float)
    dts = [max(hrs[i + j + 1] - hrs[i + j], 0.0) for j in range(H)]
    if plans is None:
        plans = enumerate_candidate_plans(e, engine.schema, horizon=H)
    cf = {}
    for name, seq in plans.items():
        samp = mc_rollout_latents(engine, z_now, np.asarray(seq)[:H], dts)  # [K,768]
        cf[name] = np.concatenate([samp.mean(0), samp.std(0)]).astype(np.float32)  # [1536]
    return {"z_now": z_now.astype(np.float32), "z_hist": z_hist.astype(np.float32), "cf": cf}


@torch.no_grad()
def _decode_baseline_labs(engine: Engine, z0: np.ndarray) -> np.ndarray:
    z = torch.tensor(z0, device=DEV).float()[None]
    return (engine.ld(z).cpu().numpy() * engine.std + engine.mean)[0]


def rollout_patient(engine: Engine, z0: np.ndarray, plans: "dict[str, np.ndarray]",
                    dts, labs_show: Optional[list] = None, baseline_plan: str = "no_treatment",
                    patient_id: Optional[int] = None, arm: Optional[str] = None,
                    actual_outcome: Optional[dict] = None) -> dict:
    """Run MC rollouts for every plan and assemble the rich output dict (see module docstring)."""
    labs_show = labs_show or [nm for nm in DEFAULT_LABS_SHOW if nm in LABN]
    dts = list(dts)
    out = {
        "patient_id": None if patient_id is None else int(patient_id),
        "arm": arm,
        "horizon_steps": len(dts),
        "MC_samples": K,
        "delta_t_hours": [round(float(x), 1) for x in dts],
        "labs_show": labs_show,
        "actual_outcome": actual_outcome,
        "plans": {},
    }
    for name, seq in plans.items():
        steps = mc_rollout(engine.model, engine.ld, engine.od, engine.mean, engine.std,
                           z0, np.asarray(seq, dtype=np.float32), dts)
        labtraj, outtraj = summarize(steps, labs_show)
        out["plans"][name] = {
            "lab_trajectory": labtraj,
            "outcome_risk_trajectory": outtraj,
            "final_mortality_risk": outtraj[-1]["mortality"],
        }

    # treatment contrast: each plan's final mortality vs a baseline plan
    ref = baseline_plan if baseline_plan in out["plans"] else next(iter(out["plans"]))
    ref_m = out["plans"][ref]["final_mortality_risk"]["mean"]
    out["treatment_contrast"] = {"baseline_plan": ref, "baseline_final_mortality": ref_m, "deltas": {}}
    for name in out["plans"]:
        if name == ref:
            continue
        m = out["plans"][name]["final_mortality_risk"]["mean"]
        out["treatment_contrast"]["deltas"][name] = round(m - ref_m, 3)

    # reliability flag: is the decoded baseline abnormal for any shown lab?
    z0lab = _decode_baseline_labs(engine, z0)
    abn = [nm for nm in labs_show
           if nm in REFS and not (REFS[nm][0] <= z0lab[LABN.index(nm)] <= REFS[nm][1])]
    out["baseline_labs"] = {nm: round(float(z0lab[LABN.index(nm)]), 2) for nm in labs_show}
    out["reliability"] = {
        "abnormal_baseline_labs": abn,
        "flag": ("RELIABLE (dynamic case — sim beats persistence here)" if abn
                 else "LOW-CONFIDENCE (stable-normal — persistence as good)"),
    }
    return out


def rollout_from_entry(engine: Engine, e: dict, horizon: int = 5,
                       plans: Optional["dict[str, np.ndarray]"] = None) -> dict:
    """Convenience: enumerate plans (unless given) and roll out a substrate entry end-to-end."""
    T = int(e["s"].shape[0])
    H = min(horizon, T - 1)
    z0 = e["s"][0]
    hrs = np.asarray(e["hours"], dtype=float)
    dts = [max(hrs[i + 1] - hrs[i], 0.0) for i in range(H)]
    if plans is None:
        plans = enumerate_candidate_plans(e, engine.schema, horizon=horizon)
    arm = str(e["outcomes"].get("arm", "medical"))
    actual = {k: int(e["outcomes"].get(k, 0) or 0) for k in OUTC}
    return rollout_patient(engine, z0, plans, dts, patient_id=int(e["patient_id"]),
                           arm=arm, actual_outcome=actual)
