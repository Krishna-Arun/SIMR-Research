"""
extract_golden_v3.py — golden-sample sanity test for v3.

For 10 deliberately-chosen matched pairs, across every model, record SIDE BY SIDE:
  - raw predicted trajectory (start -> final) for treated (A) and untreated twin (B)
  - the LOGIT PROBABILITY distribution over {rising, falling, stable}  (the "probability
    in the activation functions") — recorded as a first-class output
  - parsed direction vs argmax(logit-probs) direction  (coherence check)
  - the BENEFIT ground truth via difference-in-differences (does treatment help/hurt/none)
  - the model's predicted benefit sign
  - flags: parse!=logit, scale-off, garbage(0/None), benefit-correct

Output: inspection/golden_v3.json  (consumed by build_viewer_v3.py)
No GPU needed — uses the logit probs already stored in the v1 checkpoints.
"""
import json
import numpy as np
from pathlib import Path

BENCH = Path("/scratch/users/karun09/CAUSAL_BENCHMARK")
V3 = Path("/scratch/users/karun09/causal_benchmark_v3")
eps = {e["episode_id"]: e for e in json.loads((BENCH/"data/episodes.json").read_text())["episodes"]}
mp = json.loads((BENCH/"data/matched_pairs.json").read_text())

MODELS = [
    ("Qwen3-8B / cot",            "Qwen_Qwen3-8B_cot_ckpt.json"),
    ("Qwen3-8B / zero_shot",      "Qwen_Qwen3-8B_zero_shot_ckpt.json"),
    ("DeepSeek-R1-7B / zero_shot","deepseek-ai_DeepSeek-R1-Distill-Qwen-7B_zero_shot_ckpt.json"),
    ("DeepSeek-R1-7B / cot",      "deepseek-ai_DeepSeek-R1-Distill-Qwen-7B_cot_ckpt.json"),
]
CKPT = {n: json.loads((BENCH/"answers"/f).read_text()) for n,f in MODELS if (BENCH/"answers"/f).exists()}

def series(v):
    if isinstance(v, dict): v = v.get("resampled_values", [])
    return [float(x["value"]) if isinstance(x, dict) else float(x) for x in v]
def baseline(eid,m):
    bs=eps[eid].get("baseline_summary",{}).get(m); return bs["last_pre_value"] if bs else None
def actual_final(eid,m):
    p=series(eps[eid]["post_trajectory"]["markers"].get(m,[])); return p[-1] if p else None

def benefit_sign(fa, ba, fb, bb):
    """DiD on relative change; negative = treated resolves lower than control = 'helps' (injury marker)."""
    if None in (fa,ba,fb,bb) or ba==0 or bb==0: return None, None
    did = (fa-ba)/abs(ba) - (fb-bb)/abs(bb)
    lab = "helps" if did < -0.05 else ("hurts" if did > 0.05 else "no-different")
    return lab, round(did,3)

def model_marker(ck, eid, m):
    p = ck["predictions"].get(eid)
    if not p: return None
    tr = p["trajectories"].get(m)
    if not tr: return None
    conf = p.get("confidence") or {}
    probs = conf.get("probs") if conf.get("marker")==m else None
    return {
        "start": round(float(tr[0]),4), "final": round(float(tr[-1]),4),
        "parsed_dir": p.get("directions",{}).get(m),
        "logit_probs": {k: round(float(v),3) for k,v in probs.items()} if probs else None,
        "logit_argmax": (max(probs,key=probs.get) if probs else None),
    }

# choose 10 golden pairs spanning failure modes (same logic family as v2)
pci = [p for p in mp["pairs"] if p["contrast"]=="pci_vs_control"]
mv  = [p for p in mp["pairs"] if p["contrast"]=="multivessel_vs_singlevessel_pci"]
def hasm(p,m): return m in p.get("scored_markers",[])
chosen=[]
chosen.append(("known case + scale anomaly", next(p for p in pci if p["pair_id"]=="pair_000001")))
chosen += [("scores Sodium neg-control", p) for p in pci if hasm(p,"Sodium")][:2]
chosen += [("scores CK-MB", p) for p in pci if hasm(p,"Creatine Kinase, MB Isoenzyme") and p not in [c[1] for c in chosen]][:2]
rest=[p for p in pci if p not in [c[1] for c in chosen]]
rest.sort(key=lambda p:p["match_quality"]["score"])
chosen += [("best match-quality", rest[0]), ("worst match-quality", rest[-1])]
# treatment-HELPS vs HURTS examples by ground-truth benefit (troponin)
def gt_benefit(p):
    a,b=p["episode_a_id"],p["episode_b_id"]
    return benefit_sign(actual_final(a,"Troponin T"),baseline(a,"Troponin T"),
                        actual_final(b,"Troponin T"),baseline(b,"Troponin T"))[0]
helps=[p for p in rest if gt_benefit(p)=="helps" and p not in [c[1] for c in chosen]]
hurts=[p for p in rest if gt_benefit(p)=="hurts" and p not in [c[1] for c in chosen]]
if helps: chosen.append(("GT: treatment HELPS", helps[0]))
if hurts: chosen.append(("GT: treatment HURTS", hurts[0]))
if mv: chosen.append(("multivessel vs single", mv[0]))

golden=[]
for tag,p in chosen[:10]:
    a,b=p["episode_a_id"],p["episode_b_id"]
    markers=p.get("scored_markers",["Troponin T"])
    rec={"pair_id":p["pair_id"],"tag":tag,"contrast":p["contrast"],
         "treated":a,"untreated":b,"arm_a":p["intervention_a"],"arm_b":p["intervention_b"],
         "match_quality":p["match_quality"],"markers":markers,"per_marker":{}}
    for m in markers:
        ba,bb=baseline(a,m),baseline(b,m); fa,fb=actual_final(a,m),actual_final(b,m)
        gt_lab,gt_did=benefit_sign(fa,ba,fb,bb)
        role=eps[a]["marker_roles"].get(m,"positive")
        md={"role":role,"gt":{"baseline_a":ba,"final_a":fa,"baseline_b":bb,"final_b":fb,
                              "benefit_label":gt_lab,"did":gt_did},"models":{}}
        for name,ck in CKPT.items():
            ma,mb=model_marker(ck,a,m),model_marker(ck,b,m)
            pred_lab=None
            if ma and mb:
                pred_lab,_=benefit_sign(ma["final"],ba,mb["final"],bb)
            md["models"][name]={
                "A":ma,"B":mb,"pred_benefit":pred_lab,
                "benefit_correct": (pred_lab==gt_lab) if (pred_lab and gt_lab) else None,
                "parse_ne_logit": bool(ma and ma["parsed_dir"] and ma["logit_argmax"] and ma["parsed_dir"]!=ma["logit_argmax"]),
                "scale_off": bool(ma and ba and abs(ma["start"]-ba)/abs(ba)>0.5),
                "garbage": bool(ma and (ma["final"]==0.0 and ma["start"]==0.0)),
            }
        rec["per_marker"][m]=md
    golden.append(rec)

out=V3/"inspection"/"golden_v3.json"
out.write_text(json.dumps({"n":len(golden),"models":list(CKPT.keys()),"samples":golden},indent=2))
print(f"wrote {out} ({len(golden)} pairs, {len(CKPT)} models)")
for g in golden: print(f"  {g['pair_id']} [{g['tag']}] {g['arm_a']} vs {g['arm_b']}")
