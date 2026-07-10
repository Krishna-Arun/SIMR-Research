"""build_cf_questions.py — generate the A/B/C evaluation questions over the cardiac TEST split.

All eval patients come from data/train_substrate.pkl (so every one HAS a CLMBR latent — a hard
requirement for arms 2/3). Labels are observed reality or literature priors, NEVER the world model:
  A  intervention-attribution  -> forced choice, which of two patients underwent {procedure}; label=arm
  B  factual lab-direction      -> Benchmark-B rule on REAL remeasurements (reuses eval_simulator_benchmarkB)
  C  counterfactual sign         -> known_arrows.json pharmacology priors (add/withhold an agent)

Each record separates a SERVED view (what the LLM sees) from the answer/meta (graded out of band).
build_prompt-time rendering happens in run_arm; here we emit the structured fields + candidate_context
(patient_id + time-zero index +, for C, the agent/action to toggle) so arms 2/3 can compute rollouts.

Run: simr python build_cf_questions.py [--n_per_family 150] [--seed 0]
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from train_substrate_wm import CORE, LOINCS, LABN, ARM  # noqa: E402
from eval_simulator_benchmarkB import direction, lab_series, ref_ranges  # noqa: E402
import prompts as P  # noqa: E402

NAME2LOINC = {v: k for k, v in CORE.items()}
H_HOURS = 48.0
SHOW_LABS = ["creatinine", "bun", "potassium", "sodium", "glucose", "hemoglobin"]
ARMN = {v: k for k, v in ARM.items()}
SERVED_KEYS = {"qid", "family", "benchmark", "choices", "prompt_fields"}
OUT = HERE / "outputs"


def served_view(rec: dict) -> dict:
    """The ONLY fields an answering LLM may see. Hard-asserts no label leaks through."""
    v = {k: rec[k] for k in SERVED_KEYS if k in rec}
    assert "answer" not in v and "meta" not in v and "candidate_context" not in v, \
        f"LEAK: answer/meta/context reached served view for {rec.get('qid')}"
    # also assert the prompt text itself never contains the arm word for attribution
    return v


def obs_at(ser: dict, loinc: str, t0: pd.Timestamp):
    base = None
    for tt, vv in ser.get(loinc, []):
        if tt <= t0:
            base = vv
        else:
            break
    return base


def baseline_panel(ser: dict, t0: pd.Timestamp, labs=SHOW_LABS) -> dict:
    out = {}
    for nm in labs:
        v = obs_at(ser, NAME2LOINC[nm], t0)
        if v is not None:
            out[nm] = round(float(v), 2)
    return out


def active_meds(row: np.ndarray, columns: list) -> list:
    meds = []
    for c, on in zip(columns, row):
        if c.endswith("__on") and on > 0.5:
            meds.append(c[:-len("__on")])
    return meds


def build_B(subtest, series, refs, rng, cap):
    recs = []
    for e in subtest:
        pid = int(e["patient_id"])
        ser = series.get(pid, {})
        times = pd.to_datetime(np.asarray(e["abs_times"]))
        cols = e.get("action_cols") or json.loads((BASE / "data/action_schema.json").read_text())["columns"]
        A = np.asarray(e["action_matrix"])
        T = len(times)
        for i in range(T - 1):
            t0 = times[i]
            post_hi = t0 + pd.Timedelta(hours=H_HOURS)
            for nm in ["creatinine", "potassium", "sodium", "bun", "bicarbonate", "hemoglobin", "platelets"]:
                loinc = NAME2LOINC.get(nm)
                if loinc is None:
                    continue
                base = obs_at(ser, loinc, t0)
                if base is None:
                    continue
                post = [(tt, vv) for tt, vv in ser.get(loinc, []) if t0 < tt <= post_hi]
                if not post:
                    continue
                lo, hi = refs.get(nm, (None, None))
                ans = direction(post[-1][1], base, lo, hi)
                base_oor = lo is not None and (base < lo or base > hi)
                q, fam, ch = P.question_B_direction(nm, int(H_HOURS))
                recs.append({
                    "family": "B", "benchmark": "B", "choices": ch,
                    "prompt_fields": {
                        "baseline_labs": baseline_panel(ser, t0),
                        "active_meds": active_meds(A[i], cols),
                        "demographics": f"cardiac ICU, arm withheld",
                        "reveal_meds": True, "question": q,
                    },
                    "candidate_context": {"patient_id": pid, "tz_index": int(i), "lab": nm},
                    "answer": ans,
                    "meta": {"lab": nm, "base_oor": bool(base_oor),
                             "active": bool(float(np.abs(A[i + 1:i + 2]).sum()) > 0)},
                })
    return _balance(recs, ["Rising", "Falling", "Stable"], rng, cap)


def build_C(subtest, series, rng, cap):
    arrows = json.loads((HERE / "known_arrows.json").read_text())["arrows"]
    cols = json.loads((BASE / "data/action_schema.json").read_text())["columns"]
    cidx = {c: i for i, c in enumerate(cols)}
    all_labs = LABN
    recs = []
    for e in subtest:
        pid = int(e["patient_id"])
        ser = series.get(pid, {})
        times = pd.to_datetime(np.asarray(e["abs_times"]))
        A = np.asarray(e["action_matrix"])
        i = 0  # counterfactuals asked at admission state (time zero)
        t0 = times[i]
        base_panel = baseline_panel(ser, t0)
        for agent, targets in arrows.items():
            on_c = cidx.get(f"{agent}__on")
            if on_c is None:
                continue
            present = A[i, on_c] > 0.5
            action = "withhold" if present else "add"
            # signal targets (arrow exists)
            for lab, info in targets.items():
                if lab not in base_panel:
                    continue
                d = info["dir"]  # effect of ADDING on the lab
                if action == "add":
                    ans = "Lower" if d == "down" else "Higher"
                else:  # withholding removes the effect => opposite
                    ans = "Higher" if d == "down" else "Lower"
                q, fam, ch = P.question_C_counterfactual(agent, lab, action=action)
                recs.append(_c_rec(pid, i, agent, action, lab, ch, base_panel, A, cols, ans,
                                   "known_arrow", info.get("mechanism")))
            # an Unchanged distractor: a lab this agent has no arrow for
            no_arrow = [l for l in all_labs if l in base_panel and l not in targets]
            if no_arrow:
                lab = no_arrow[int(rng.integers(len(no_arrow)))]
                q, fam, ch = P.question_C_counterfactual(agent, lab, action=action)
                recs.append(_c_rec(pid, i, agent, action, lab, ch, base_panel, A, cols,
                                   "Unchanged", "no_established_effect", None))
    return _balance(recs, ["Higher", "Lower", "Unchanged"], rng, cap)


def _c_rec(pid, i, agent, action, lab, ch, base_panel, A, cols, ans, src, mech):
    return {
        "family": "C", "benchmark": "C", "choices": ch,
        "prompt_fields": {
            "baseline_labs": base_panel,
            "active_meds": active_meds(A[i], cols),
            "demographics": "cardiac ICU, arm withheld",
            "reveal_meds": True,
            "question": P.question_C_counterfactual(agent, lab, action=action)[0],
        },
        "candidate_context": {"patient_id": int(pid), "tz_index": int(i),
                              "agent": agent, "action": action, "lab": lab},
        "answer": ans,
        "meta": {"agent": agent, "action": action, "lab": lab, "answer_source": src, "mechanism": mech},
    }


def build_A(subtest, series, rng, cap):
    """Forced-choice attribution: which of two patients underwent {procedure}."""
    recs = []
    for proc_arm, proc_name in [("pci", "PCI"), ("cabg", "CABG")]:
        pos = [e for e in subtest if str(e["outcomes"].get("arm")) == proc_arm]
        neg = [e for e in subtest if str(e["outcomes"].get("arm")) == "medical"]
        rng.shuffle(pos)
        rng.shuffle(neg)
        n = min(len(pos), len(neg), cap // 2)
        for k in range(n):
            ep, en = pos[k], neg[k]
            # random ordering of which is "Patient A"
            pos_is_A = bool(rng.integers(2))
            eA, eB = (ep, en) if pos_is_A else (en, ep)
            recs.append({
                "family": "A", "benchmark": "A", "choices": P.CHOICES["A"],
                "prompt_fields": {
                    "patient_A": _attr_case(eA, series),
                    "patient_B": _attr_case(eB, series),
                    "question": P.question_A_attribution(proc_name)[0],
                },
                "candidate_context": {"patient_id_A": int(eA["patient_id"]),
                                      "patient_id_B": int(eB["patient_id"]),
                                      "procedure": proc_arm},
                "answer": "A" if pos_is_A else "B",
                "meta": {"procedure": proc_name},
            })
    rng.shuffle(recs)
    return recs[:cap]


def _attr_case(e, series):
    """Observed pre/post lab trajectory for a patient, treatments hidden (they are the answer)."""
    pid = int(e["patient_id"])
    ser = series.get(pid, {})
    times = pd.to_datetime(np.asarray(e["abs_times"]))
    t0, tN = times[0], times[-1]
    return {
        "baseline_labs": baseline_panel(ser, t0),
        "later_labs": baseline_panel(ser, tN),
        "hours_observed": round(float((tN - t0).total_seconds() / 3600.0), 1),
    }


def _balance(recs, classes, rng, cap):
    by = defaultdict(list)
    for r in recs:
        by[r["answer"]].append(r)
    per = max(1, cap // len(classes))
    out = []
    for c in classes:
        pool = by.get(c, [])
        rng.shuffle(pool)
        out += pool[:per]
    rng.shuffle(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_per_family", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    sub = pickle.load(open(BASE / "data/train_substrate.pkl", "rb"))
    traj = pickle.load(open(BASE / "data/trajectories.pkl", "rb"))
    sp = json.loads((BASE / "data/splits.json").read_text())
    test = set(sp["splits"]["test"])
    subtest = [e for e in sub if int(e["patient_id"]) in test]
    series = lab_series(traj)
    refs = ref_ranges()
    print(f"TEST substrate entries: {len(subtest)}  (all have CLMBR latents by construction)")

    B = build_B(subtest, series, refs, rng, args.n_per_family)
    C = build_C(subtest, series, rng, args.n_per_family)
    A = build_A(subtest, series, rng, min(args.n_per_family, 80))

    allq = []
    for k, r in enumerate(A + B + C):
        r["qid"] = f"{r['family']}_{k:04d}"
        allq.append(r)

    # ---- gates ----
    # 1) leakage: served view carries no answer/meta/context, and no arm word in attribution text
    for r in allq:
        v = served_view(r)
        blob = json.dumps(v).lower()
        if r["family"] == "A":
            assert "medical" not in blob and "arm" not in blob, f"arm leak in {r['qid']}"
    # 2) every referenced patient is in the test split (and thus has a CLMBR latent)
    for r in allq:
        cc = r["candidate_context"]
        pids = [cc[k] for k in cc if k.startswith("patient_id")]
        for p in pids:
            assert p in test, f"{r['qid']} references non-test patient {p}"
    # 3) balance report
    dist = {fam: dict(Counter(r["answer"] for r in allq if r["family"] == fam)) for fam in "ABC"}

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "cf_questions.jsonl", "w") as f:
        for r in allq:
            f.write(json.dumps(r) + "\n")
    summary = {"n_total": len(allq), "by_family": {fam: sum(r["family"] == fam for r in allq) for fam in "ABC"},
               "answer_distribution": dist, "seed": args.seed, "n_test_patients": len(subtest)}
    (OUT / "cf_questions_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {OUT/'cf_questions.jsonl'}  (leakage + test-membership gates PASSED)")

    # show one served example per family
    for fam in "ABC":
        ex = next(r for r in allq if r["family"] == fam)
        print(f"\n=== served view example (family {fam}) ===")
        print(json.dumps(served_view(ex), indent=2)[:900])


if __name__ == "__main__":
    main()
