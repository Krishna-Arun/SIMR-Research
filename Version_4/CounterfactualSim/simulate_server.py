#!/usr/bin/env python3
"""
CF-sim MCP tool server (stdio, dependency-light) — exposes simulate() to the answering LLM.

Tool:
  simulate(patient_id, intervention) -> counterfactual prediction under `intervention`:
     {predicted_lab_directions:{lab:Rising|Falling|Stable},
      predicted_lab_values:{lab:{mean,lo,hi}},        # 80% MC band, real units
      mortality_1y_risk, mortality_1y_band:[lo,hi], readmission_30d_risk, backend}

Backends (auto-selected):
  - trained_enriched : if $CFSIM_CKPT points to world_model_enriched.pt AND torch is available,
        load the AC-JEPA predictor + lab/outcome decoders, take the patient's anchor CLMBR latent,
        set the action to the requested arm, and MONTE-CARLO roll the latent forward
        (z_{t+1}=z_t+Δz, Δz~N(μ,σ²), K=64) over a 72h horizon; decode to 14 labs + mortality
        with uncertainty bands. This is the real counterfactual engine.
  - heuristic (default) : dependency-free physiology priors per intervention family — lets the
        RL environment + ablations run before/without the trained model. Clearly labeled.

Speaks the minimal MCP JSON-RPC (initialize / tools/list / tools/call), same as
Benchmark_A/MCP_Server/server.py. Runs on Python 3.9 (system torch/pandas present).
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# physiology priors: intervention family -> expected direction of key labs
HEURISTIC = {
    "dialysis":   {"Creatinine": "Falling", "Urea Nitrogen": "Falling", "Potassium": "Falling",
                   "Bicarbonate": "Rising"},
    "transfusion": {"Hemoglobin": "Rising", "Hematocrit": "Rising", "Red Blood Cells": "Rising"},
    "ventilation": {"pCO2": "Falling", "pO2": "Rising"},
    "none":       {},
}
_OUTCOME_PRIOR = {"dialysis": 0.30, "transfusion": 0.20, "ventilation": 0.35, "none": 0.15}

# rollout config
_K = 64          # Monte-Carlo samples
_H = 3           # rollout steps
_DT = 24.0       # hours per step (3 x 24h = 72h horizon, matches the B benchmark)
_STABLE_EPS = 0.15   # |Δ| (std units) below which a lab is called "Stable"

_engine = None


def _parse_dt(s):
    import datetime as _dt
    if isinstance(s, _dt.datetime):
        return s
    s = str(s).replace("T", " ").strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(s[:19] if len(s) >= 19 else s, f)
        except ValueError:
            continue
    return None


def _load_engine():
    """Load the enriched AC-JEPA world model + decoders from $CFSIM_CKPT. Returns a dict
    engine, or False (→ heuristic) if the ckpt/torch/embeddings are unavailable."""
    global _engine
    if _engine is not None:
        return _engine
    ckpt = os.environ.get("CFSIM_CKPT")
    if not ckpt or not os.path.exists(ckpt):
        _engine = False
        return _engine
    try:
        import torch
        sys.path.insert(0, _HERE)
        from ac_jepa import ACJEPAPredictor, LabDecoder, OutcomeDecoder  # noqa

        st = torch.load(ckpt, map_location="cpu", weights_only=False)
        sch = st["schema"]
        pred = ACJEPAPredictor(sch["state_dim"], sch["action_dim"], n_arms=len(sch["arm_classes"]))
        pred.load_state_dict(st["predictor"]); pred.eval()
        lab = LabDecoder(sch["state_dim"], sch["n_labs"]); lab.load_state_dict(st["lab_decoder"]); lab.eval()
        out = OutcomeDecoder(sch["state_dim"]); out.load_state_dict(st["outcome_decoder"]); out.eval()

        idx_path = os.path.join(_HERE, "embeddings", "index.json")
        index = json.load(open(idx_path))["patients"] if os.path.exists(idx_path) else {}
        act_path = os.path.join(os.path.dirname(ckpt), "sim_patient_actions.json")
        pat_act = json.load(open(act_path)) if os.path.exists(act_path) else {}

        import numpy as np
        _engine = {"torch": torch, "np": np, "pred": pred, "lab": lab, "out": out,
                   "mean": np.asarray(st["lab_mean"], "float32"),
                   "std": np.asarray(st["lab_std"], "float32"),
                   "schema": sch, "index": index, "pat_act": pat_act}
    except Exception as e:
        sys.stderr.write(f"[cfsim] enriched engine unavailable: {type(e).__name__}: {e}\n")
        _engine = False
    return _engine


def _anchor_latent(eng, patient_id):
    """Load the patient's CLMBR states and return the latent at the pre-intervention anchor."""
    np = eng["np"]
    meta = eng["index"].get(str(patient_id))
    if not meta:
        return None
    npy = os.path.join(_HERE, "embeddings", os.path.basename(meta["path"]))
    if not os.path.exists(npy):
        return None
    z = np.load(npy).astype("float32")
    ev = meta.get("event_times", [])
    T = min(len(z), len(ev))
    if T == 0:
        return None
    anchor = _parse_dt(meta["anchor_time"])
    pre = [i for i in range(T) if (_parse_dt(ev[i]) or anchor) <= anchor]
    return z[pre[-1] if pre else T - 1]


def _simulate_trained(eng, patient_id, fam):
    torch, np = eng["torch"], eng["np"]
    sch = eng["schema"]
    z0 = _anchor_latent(eng, patient_id)
    if z0 is None:
        return None
    # build 34-d action: arm one-hot for the counterfactual `fam` + the patient's procedures
    a = np.zeros(sch["action_dim"], "float32")
    arms = sch["action_arms"]
    a[arms.index(fam) if fam in arms else 0] = 1.0
    pa = eng["pat_act"].get(str(patient_id))
    if pa:
        proc = pa.get("proc_at_anchor", [])
        a[len(arms):len(arms) + len(proc)] = np.asarray(proc, "float32")
    zt = torch.from_numpy(z0).unsqueeze(0)            # [1,768]
    at = torch.from_numpy(a).unsqueeze(0)             # [1,34]
    dtt = torch.tensor([_DT], dtype=torch.float32)

    with torch.no_grad():
        base_lab = eng["lab"](zt).numpy()[0]          # standardized baseline labs at anchor
        # K Monte-Carlo rollouts of H steps
        Z = zt.repeat(_K, 1)                          # [K,768]
        A = at.repeat(_K, 1); DT = dtt.repeat(_K)
        for _ in range(_H):
            Z = eng["pred"].sample_next(Z, A, DT)     # z + Δz, Δz~N(μ,σ²)
        lab_std = eng["lab"](Z).numpy()               # [K,14] standardized
        mort = torch.sigmoid(eng["out"](Z)).numpy()   # [K]

    mean_std = lab_std.mean(0); p10 = np.percentile(lab_std, 10, 0); p90 = np.percentile(lab_std, 90, 0)
    mu, sd = eng["mean"], eng["std"]
    names = sch["lab_names"]
    directions, values = {}, {}
    for j, nm in enumerate(names):
        d = mean_std[j] - base_lab[j]                 # standardized change over horizon
        directions[nm] = ("Stable" if abs(d) < _STABLE_EPS else ("Rising" if d > 0 else "Falling"))
        values[nm] = {"mean": round(float(mean_std[j] * sd[j] + mu[j]), 2),
                      "lo": round(float(p10[j] * sd[j] + mu[j]), 2),
                      "hi": round(float(p90[j] * sd[j] + mu[j]), 2)}
    return {"patient_id": str(patient_id), "intervention": fam, "backend": "trained_enriched",
            "predicted_lab_directions": directions,
            "predicted_lab_values": values,
            "mortality_1y_risk": round(float(mort.mean()), 3),
            "mortality_1y_band": [round(float(np.percentile(mort, 10)), 3),
                                  round(float(np.percentile(mort, 90)), 3)],
            "horizon_hours": int(_H * _DT), "mc_samples": _K,
            "note": ("AC-JEPA counterfactual rollout: z+μ residual transition, K=64 MC sampling "
                     "of Δz~N(μ,σ²) over 72h, decoded to labs + 1y-mortality with 80% bands")}


def simulate(patient_id: str, intervention: str) -> dict:
    fam = str(intervention).strip().lower()
    fam = next((f for f in HEURISTIC if f in fam), "none")
    eng = _load_engine()
    if eng and eng is not False:
        try:
            out = _simulate_trained(eng, patient_id, fam)
            if out is not None:
                return out
        except Exception as e:
            sys.stderr.write(f"[cfsim] trained simulate failed: {type(e).__name__}: {e}\n")
    return {"patient_id": patient_id, "intervention": fam, "backend": "heuristic",
            "predicted_lab_directions": HEURISTIC[fam],
            "mortality_1y_risk": _OUTCOME_PRIOR[fam],
            "note": "heuristic priors — set CFSIM_CKPT to world_model_enriched.pt for the trained engine"}


TOOLS = [{
    "name": "simulate",
    "description": ("Simulate the counterfactual 72h future for a patient under an intervention "
                    "(dialysis/transfusion/ventilation/none). Returns predicted post-intervention "
                    "lab directions + values (with uncertainty) and 1-year mortality risk."),
    "inputSchema": {"type": "object", "properties": {
        "patient_id": {"type": "string"}, "intervention": {"type": "string"}},
        "required": ["patient_id", "intervention"]},
    "fn": lambda a: simulate(a["patient_id"], a["intervention"])}]
_BY_NAME = {t["name"]: t for t in TOOLS}


def _send(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params", {})
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "cfsim", "version": "0.2-enriched"}}})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "tools": [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]}})
        elif method == "tools/call":
            t = _BY_NAME.get((params or {}).get("name"))
            args = (params or {}).get("arguments", {}) or {}
            if not t:
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": "unknown tool"}], "isError": True}})
                continue
            try:
                out = t["fn"](args)
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(out)}], "isError": False}})
            except Exception as e:  # noqa: BLE001
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}})
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": str(method)}})


if __name__ == "__main__":
    main()
