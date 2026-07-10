"""
score_v3.py — Counterfactual Treatment Benefit (CTB) scorer.

Scores, with ONE coherent metric, whether a predictor knows if treatment HELPS / HURTS /
does NOTHING for a patient, relative to a matched untreated twin.

Ground truth (per matched pair, per marker):
  effect_treated  = (final_A - baseline_A)/|baseline_A|      # change from each arm's OWN baseline
  effect_control  = (final_B - baseline_B)/|baseline_B|
  DiD             = effect_treated - effect_control          # the causal contrast
  benefit label   = helps  if DiD < -TAU   (treated resolves lower = better, injury marker)
                    hurts  if DiD > +TAU
                    no-different otherwise
  NEGATIVE CONTROL (sodium): truth is ALWAYS 'no-different' by construction (no causal pathway).

Why the lazy cheater dies:
  - copy-baseline  -> predicts DiD=0 -> 'no-different' everywhere -> fails every helps/hurts pair.
  - always-'helps' -> fails every hurts / no-different pair AND the negative control.
  - baseline ordering carries ZERO signal (DiD subtracts each arm's own baseline).
Reported: overall acc, acc on the decisive (helps|hurts) subset, negative-control false-effect
rate, well-formed rate (validity gate), and calibration ECE on the recorded class probability.

Runs three reference oracles + every model checkpoint. Parameterised by OUTCOME so the same
scorer runs on the confounded 96h outcome (demo) or the re-extracted long-horizon benefit outcome.
"""
import json, argparse
import numpy as np
from pathlib import Path
from collections import defaultdict

BENCH = Path("/scratch/users/karun09/CAUSAL_BENCHMARK")
V3 = Path("/scratch/users/karun09/causal_benchmark_v3")
TAU = 0.10   # effect-size threshold: |DiD| must exceed this to count as helps/hurts

eps = {e["episode_id"]: e for e in json.loads((BENCH/"data/episodes.json").read_text())["episodes"]}
mp = json.loads((BENCH/"data/matched_pairs.json").read_text())

MODELS = [
    ("Qwen3-8B/cot","Qwen_Qwen3-8B_cot_ckpt.json"),
    ("Qwen3-8B/zero","Qwen_Qwen3-8B_zero_shot_ckpt.json"),
    ("DeepSeek-R1-7B/zero","deepseek-ai_DeepSeek-R1-Distill-Qwen-7B_zero_shot_ckpt.json"),
    ("DeepSeek-R1-7B/cot","deepseek-ai_DeepSeek-R1-Distill-Qwen-7B_cot_ckpt.json"),
]

def series(v):
    if isinstance(v,dict): v=v.get("resampled_values",[])
    return [float(x["value"]) if isinstance(x,dict) else float(x) for x in v]
def baseline(eid,m):
    bs=eps[eid].get("baseline_summary",{}).get(m); return bs["last_pre_value"] if bs else None
def actual_final(eid,m):
    p=series(eps[eid]["post_trajectory"]["markers"].get(m,[])); return p[-1] if p else None
def slope(eid,m):
    bs=eps[eid].get("baseline_summary",{}).get(m); return bs.get("slope_per_h",0.0) if bs else 0.0

def label(did, role):
    if role=="negative_control": return "no-different"   # truth fixed by construction
    if did is None: return None
    return "helps" if did<-TAU else ("hurts" if did>TAU else "no-different")

def did_of(fa,ba,fb,bb):
    if None in (fa,ba,fb,bb) or ba==0 or bb==0: return None
    return (fa-ba)/abs(ba) - (fb-bb)/abs(bb)

def gt_label(p,m,role):
    a,b=p["episode_a_id"],p["episode_b_id"]
    return label(did_of(actual_final(a,m),baseline(a,m),actual_final(b,m),baseline(b,m)), role)

# ── predictors ──────────────────────────────────────────────────────────────
def oracle_final(kind,eid,m,arm,role):
    b=baseline(eid,m)
    if b is None: return None
    if kind=="baseline_copy": return b
    if kind=="always_helps":
        # naive "the treatment helps everything" cheater: improves the TREATED arm on ALL
        # markers (incl. the negative control), leaves control arm unchanged. Under DiD this
        # yields 'helps' everywhere -> must blow up the negative-control false-effect rate.
        return b*0.5 if arm in ("pci","cabg") else b
    if kind=="pretrend":      return b+slope(eid,m)*96.0
    if kind=="physiology":
        if role=="negative_control": return b
        return b*1.30 if arm in ("pci","cabg") else b*0.70   # NOTE: 96h hump-aware; long-horizon flips to resolution
    return None

def model_final(ck,eid,m):
    p=ck["predictions"].get(eid)
    if not p: return None,None,None
    tr=p["trajectories"].get(m)
    if not tr: return None,None,None
    conf=p.get("confidence") or {}
    probs=conf.get("probs") if conf.get("marker")==m else None
    return float(tr[-1]), float(tr[0]), probs

def arm_norm(a): return a.replace("pci_multivessel","pci").replace("pci_singlevessel","pci")

def score_predictor(get_final, name, want_probs=False):
    """Returns metrics dict. get_final(eid,m,arm,role)->(final,start,probs|None)."""
    tot=correct=0; dec_tot=dec_correct=0
    nc_tot=nc_fp=0; wf=0; n=0
    cal=[]  # (confidence, correct_direction) for ECE on treated-arm direction
    by_cluster=defaultdict(lambda:[0,0])  # treated_eid -> [correct,total] for cluster-robust
    for p in mp["pairs"]:
        a,b=p["episode_a_id"],p["episode_b_id"]
        for m in p.get("scored_markers",[]):
            role=eps[a]["marker_roles"].get(m,"positive")
            gl=gt_label(p,m,role)
            if gl is None: continue
            fa,sa,pa=get_final(a,m,arm_norm(p["intervention_a"]),role)
            fb,sb,pb=get_final(b,m,arm_norm(p["intervention_b"]),role)
            n+=1
            # validity gate: garbage / missing -> abstention (not scored as correct)
            if fa is None or fb is None or (fa==0 and sa==0):
                continue
            wf+=1
            ba,bb=baseline(a,m),baseline(b,m)
            # prediction is labelled FREELY (no negative-control override) so that predicting
            # any effect on the negative control is detected as a false positive.
            pl=label(did_of(fa,ba,fb,bb), "positive")
            tot+=1; ok=(pl==gl); correct+=int(ok)
            by_cluster[a][0]+=int(ok); by_cluster[a][1]+=1
            if role=="negative_control":
                nc_tot+=1; nc_fp+=int(pl!="no-different")   # predicting any effect on sodium = false positive
            if gl in ("helps","hurts"):
                dec_tot+=1; dec_correct+=int(ok)
            # calibration on treated-arm direction (where logit probs exist)
            if want_probs and pa:
                conf=max(pa.values()); pred_dir=max(pa,key=pa.get)
                # actual treated direction from its own baseline
                ch=(fa-ba)/abs(ba) if ba else 0
                tdir="stable" if abs(ch)<0.15 else ("rising" if ch>0 else "falling")
                cal.append((conf, int(pred_dir==tdir)))
    # cluster-robust accuracy: average per-treated-patient accuracy (each patient weighted once)
    cluster_acc=np.mean([c/t for c,t in by_cluster.values() if t]) if by_cluster else float("nan")
    ece=None
    if cal:
        conf=np.array([c for c,_ in cal]); corr=np.array([c for _,c in cal])
        bins=np.linspace(0,1,6); e=0.0
        for i in range(5):
            mlo,mhi=bins[i],bins[i+1]
            mm=(conf>=mlo)&(conf< mhi if i<4 else conf<=mhi)
            if mm.sum(): e+=mm.mean()*abs(corr[mm].mean()-conf[mm].mean())
        ece=round(float(e),3)
    return {"name":name,
            "acc": round(correct/tot,3) if tot else None,
            "acc_cluster_robust": round(float(cluster_acc),3) if cluster_acc==cluster_acc else None,
            "acc_decisive(helps|hurts)": round(dec_correct/dec_tot,3) if dec_tot else None,
            "neg_control_false_effect_rate": round(nc_fp/nc_tot,3) if nc_tot else None,
            "well_formed_rate": round(wf/n,3) if n else None,
            "calibration_ece": ece, "n_scored": tot}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--label",default="96h outcome (CONFOUNDED demo)")
    args=ap.parse_args()
    rows=[]
    for kind in ["baseline_copy","always_helps","pretrend","physiology"]:
        rows.append(score_predictor(lambda e,m,arm,role,k=kind: (oracle_final(k,e,m,arm,role),
                                    0 if oracle_final(k,e,m,arm,role) is None else 1, None),
                                    f"[oracle] {kind}"))
    for name,fn in MODELS:
        f=BENCH/"answers"/fn
        if not f.exists(): continue
        ck=json.loads(f.read_text())
        rows.append(score_predictor(lambda e,m,arm,role,ck=ck: model_final(ck,e,m), name, want_probs=True))

    print(f"\nCounterfactual Treatment Benefit (CTB) — TAU={TAU} — outcome: {args.label}\n")
    hdr=["predictor","acc","clu-rob","decisive","NC-FP↓","wellform","ECE↓","n"]
    print("%-26s%7s%9s%10s%8s%9s%6s%6s"%tuple(hdr)); print("-"*92)
    for r in rows:
        print("%-26s%7s%9s%10s%8s%9s%6s%6s"%(
            r["name"][:26], r["acc"], r["acc_cluster_robust"], r["acc_decisive(helps|hurts)"],
            r["neg_control_false_effect_rate"], r["well_formed_rate"], r["calibration_ece"], r["n_scored"]))
    (V3/"outputs"/"ctb_scores.json").write_text(json.dumps(rows,indent=2))
    print(f"\nwrote {V3/'outputs'/'ctb_scores.json'}")
    print("\nReading: lazy 'baseline_copy' should win acc by saying no-different, but its")
    print("decisive(helps|hurts) accuracy collapses -> it cannot tell when treatment matters.")
    print("'always_helps' should blow up the NC-FP rate. A real reasoner needs HIGH decisive acc AND LOW NC-FP.")

if __name__=="__main__": main()
