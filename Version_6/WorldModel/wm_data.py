#!/usr/bin/env python3
"""
World-Model dataset builder (V6) -- HOURLY GRID, essentials only.

Each patient's pre-anchor window -> a grid [H hours x C channels x 4 features].
  Channels = tracked labs  +  medication-dose channels.
  Cell features = [z_value, ref_pos, mask, staleness].
    - labs: real draws (mask=1, staleness=0); gaps forward-filled (mask=0, staleness>0).
    - meds: dose present across the window (no per-hour timing in the B state), mask=1.
Static  = comorbidity flags + age + sex.
Action  = [is_dialysis, is_diuretic, dialysis_dur_norm, diuretic_dose_ratio_norm].
Target  = standardized post-window value for the 4 target labs (+ mask + pieces to
          derive Benchmark-B reference-range membership at eval).

No CRN / IPW / matched-contrast / GRU-D here -- just the encoder + action + lab head.
"""
import ast, json, math, os, random
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)
DIALYSIS = f"{V6}/Benchmark_B/cases_eligible_all4.jsonl"
DIURETIC = f"{V6}/Benchmark_B_diuretic/cases_eligible_all4.jsonl"

H = 48                      # hours in the pre-anchor window
POST_H = 72                 # hours in the post-anchor window (hour-by-hour targets)
FEAT = 4                    # [z_value, ref_pos, mask, staleness]
N_MED_CHANNELS = 20         # top-K medication classes; rest -> __other_med__
TARGET_LABS = ["Creatinine", "BUN (Urea Nitrogen)", "Potassium", "Bicarbonate"]
COMORBID = ["aki", "ckd_nonesrd", "diabetes", "sepsis", "hypertension",
            "cardiogenic_shock", "atrial_fib", "cad", "copd", "liver_disease"]
LABELS = ["moved_into_range", "stayed", "moved_out_of_range"]


def status_of(v, lo, hi):
    if v is None or lo is None or hi is None: return "Within"
    if v < lo: return "Below"
    if v > hi: return "Above"
    return "Within"

def label_from(bs, ps):
    if ps == "Within" and bs != "Within": return "moved_into_range"
    if bs == "Within" and ps != "Within": return "moved_out_of_range"
    return "stayed"

def _fnum(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def hour_bucket(hb):
    """hours-before-anchor (positive) -> grid row in [0,H-1]; H-1 = hour before anchor."""
    return H - int(math.ceil(max(hb, 1e-6)))


def _parse(case, cohort):
    st = case["state"]
    # labs: lab -> list of (hb, value, lo, hi)
    labs = defaultdict(list)
    for lab, rows in st.get("pre_window_target_labs", {}).items():
        for r in rows:
            h = _fnum(r.get("h"))
            if h is not None:
                labs[lab].append((-h, _fnum(r.get("v")), _fnum(r.get("ref_low")), _fnum(r.get("ref_high"))))
    for lab, r in st.get("context_labs_baseline", {}).items():
        hb = _fnum(r.get("hours_before"))
        if hb is not None:
            labs[lab].append((abs(hb), _fnum(r.get("value")), _fnum(r.get("ref_low")), _fnum(r.get("ref_high"))))
    # meds: class -> max dose seen
    meds = {}
    for cls, rows in st.get("medications_pre_window", {}).items():
        dose = None
        for r in rows:
            dv = _fnum(r.get("dose_val"))
            if dv is not None: dose = max(dose or 0.0, dv)
        meds[cls] = dose
    # static
    demo = st.get("demographics", {})
    static = dict(comorbid=[1.0 if st.get("comorbidities", {}).get(f) else 0.0 for f in COMORBID],
                  age=_fnum(demo.get("age")), sex=1.0 if demo.get("gender") == "M" else 0.0)
    # action
    if cohort == "dialysis":
        dur = _fnum((case.get("dialysis") or {}).get("duration_hours")) or 0.0
        action = [1.0, 0.0, min(dur / 48.0, 3.0), 0.0]
    else:
        esc = case.get("escalation") or {}
        frm = _fnum(esc.get("from_mg_furos_eq")) or 1.0
        to = _fnum(esc.get("to_mg_furos_eq")) or frm
        action = [0.0, 1.0, 0.0, min((to / frm if frm else 1.0) / 4.0, 3.0)]
    # targets
    tg = case["outcome"]["targets"]
    targets, mask, bstat, bval, refs, labels = [], [], [], [], [], []
    for lab in TARGET_LABS:
        t = tg[lab]
        targets.append(_fnum(t.get("post_value")))
        mask.append(1.0 if t.get("post_value") is not None else 0.0)
        bstat.append(t.get("baseline_status", "Within"))
        bval.append(_fnum(t.get("baseline_value")))
        refs.append(t.get("baseline_ref", [None, None]))
        labels.append(t.get("label", "stayed"))
    # POST-anchor hourly target series (stored in outcome.post_window_target_labs)
    post = {}
    pw = case["outcome"].get("post_window_target_labs", {})
    for lab in TARGET_LABS:
        post[lab] = [(_fnum(r.get("h")), _fnum(r.get("v"))) for r in pw.get(lab, [])
                     if _fnum(r.get("h")) is not None and _fnum(r.get("v")) is not None]
    return dict(hadm=str(case["hadm_id"]), subject=str(case["subject_id"]), cohort=cohort,
                labs=dict(labs), meds=meds, static=static, action=action, targets=targets,
                mask=mask, bstat=bstat, bval=bval, refs=refs, labels=labels, post=post)


def load_raw():
    out = []
    for path, cohort in [(DIALYSIS, "dialysis"), (DIURETIC, "diuretic")]:
        for l in open(path):
            c = json.loads(l)
            tg = c["outcome"]["targets"]
            if all(tg.get(lab, {}).get("eligible") for lab in TARGET_LABS):
                out.append(_parse(c, cohort))
    return out


def benchmark_subjects(all_cases):
    """Subjects that appear in the benchmark EVAL sets -> held out of WM training.
    Anchored on Benchmark C's matched pairs (the counterfactual eval); Benchmark A's
    complete-set backbone is a subset of these. Mapped hadm->subject via the loaded
    cases plus the Benchmark-A index as fallback."""
    h2s = {e["hadm"]: e["subject"] for e in all_cases}
    idxp = f"{V6}/Benchmark_A/index/cases_index.json"
    if os.path.exists(idxp):
        for e in json.load(open(idxp)).values():
            h2s.setdefault(str(e["hadm_id"]), str(e["subject_id"]))
    cpath = f"{V6}/Benchmark_C/cases_c.jsonl"
    bench = set()
    if os.path.exists(cpath):
        for l in open(cpath):
            it = json.loads(l)
            m = it["meta"] if isinstance(it["meta"], dict) else ast.literal_eval(it["meta"])
            for k in ("dialysis_hadm", "diuresis_hadm"):
                s = h2s.get(str(m.get(k)))
                if s: bench.add(s)
    return bench


def build(seed=20260714, val_frac=0.15, test_frac=0.20):
    ex = load_raw()
    # ACTION-STRATIFIED subject-level split: train/val/test share the same
    # dialysis:diuretic mix, so the WM is not tested out-of-distribution. Split by
    # subject_id (a subject with any dialysis case -> dialysis stratum) so no patient
    # leaks across splits. The split is persisted for the benchmark eval scripts to
    # reuse -> the same held-out patients feed both the WM and the LLM baselines.
    subj_action = {}
    for e in ex:
        if e["cohort"] == "dialysis":
            subj_action[e["subject"]] = "dialysis"
        else:
            subj_action.setdefault(e["subject"], "diuretic")
    rng = random.Random(seed)
    test_subj, val_subj = set(), set()
    for strat in ("dialysis", "diuretic"):
        subs = sorted(s for s, a in subj_action.items() if a == strat)
        rng.shuffle(subs)
        n_te = int(len(subs) * test_frac)
        n_va = int(len(subs) * val_frac)
        test_subj |= set(subs[:n_te])
        val_subj |= set(subs[n_te:n_te + n_va])
    train = [e for e in ex if e["subject"] not in test_subj and e["subject"] not in val_subj]
    val = [e for e in ex if e["subject"] in val_subj]
    test = [e for e in ex if e["subject"] in test_subj]
    json.dump({"seed": seed, "test_frac": test_frac, "val_frac": val_frac,
               "train_subjects": sorted({e["subject"] for e in train}),
               "val_subjects": sorted(val_subj), "test_subjects": sorted(test_subj)},
              open(os.path.join(HERE, "split.json"), "w"))

    # ---- channels from TRAIN ----
    lab_names = sorted({lab for e in train for lab in e["labs"]})
    med_freq = Counter(cls for e in train for cls in e["meds"])
    med_top = [c for c, _ in med_freq.most_common(N_MED_CHANNELS)]
    channels = [("lab", l) for l in lab_names] + [("med", m) for m in med_top] + [("med", "__other_med__")]
    chan_index = {c: i for i, c in enumerate(channels)}

    # ---- scalers from TRAIN ----
    labvals = defaultdict(list); meddose = defaultdict(list); ages = []
    for e in train:
        for lab, rows in e["labs"].items():
            for (_, v, _, _) in rows:
                if v is not None: labvals[lab].append(v)
        for lab, tv in zip(TARGET_LABS, e["targets"]):
            if tv is not None: labvals[lab].append(tv)
        for cls, dose in e["meds"].items():
            ch = cls if ("med", cls) in chan_index else "__other_med__"
            if dose is not None: meddose[ch].append(math.log1p(dose))
        if e["static"]["age"] is not None: ages.append(e["static"]["age"])
    def stats(xs):
        if not xs: return (0.0, 1.0)
        m = sum(xs) / len(xs); sd = (sum((x - m) ** 2 for x in xs) / max(len(xs) - 1, 1)) ** 0.5 or 1.0
        return (m, sd)
    scaler = dict(lab={l: stats(v) for l, v in labvals.items()},
                  med={c: stats(v) for c, v in meddose.items()},
                  age=stats(ages))

    meta = dict(H=H, C=len(channels), feat=FEAT, n_static=len(COMORBID) + 2,
                n_labs=len(TARGET_LABS), action_dim=4, target_labs=TARGET_LABS,
                labels=LABELS, n_train=len(train), n_val=len(val), n_test=len(test),
                dialysis_frac=dict(
                    train=round(sum(e["cohort"] == "dialysis" for e in train) / max(len(train), 1), 3),
                    test=round(sum(e["cohort"] == "dialysis" for e in test) / max(len(test), 1), 3)),
                n_lab_channels=len(lab_names), n_med_channels=len(med_top) + 1)
    return train, val, test, channels, chan_index, scaler, meta


def _refpos(v, lo, hi):
    if v is None or lo is None or hi is None or hi <= lo: return 0.0
    return max(-3.0, min(3.0, (v - lo) / (hi - lo)))


def featurize(e, channels, chan_index, scaler):
    """-> grid [H, C, 4] (list of lists) and active [H, C] (0/1)."""
    C = len(channels)
    grid = [[[0.0] * FEAT for _ in range(C)] for _ in range(H)]
    active = [[0.0] * C for _ in range(H)]
    # labs: bucket -> LOCF forward-fill
    for lab, rows in e["labs"].items():
        ci = chan_index.get(("lab", lab))
        if ci is None: continue
        m, sd = scaler["lab"].get(lab, (0.0, 1.0))
        bucket = {}
        for (hb, v, lo, hi) in sorted(rows):                 # ascending hb == descending recency
            t = hour_bucket(hb)
            if 0 <= t < H and v is not None:
                bucket[t] = ((v - m) / sd, _refpos(v, lo, hi))
        last = None; last_t = None
        for t in range(H):
            if t in bucket:
                z, rp = bucket[t]; grid[t][ci] = [z, rp, 1.0, 0.0]; active[t][ci] = 1.0
                last = (z, rp); last_t = t
            elif last is not None:
                grid[t][ci] = [last[0], last[1], 0.0, min((t - last_t) / 24.0, 3.0)]; active[t][ci] = 1.0
    # meds: constant dose channel across the window
    for cls, dose in e["meds"].items():
        key = ("med", cls) if ("med", cls) in chan_index else ("med", "__other_med__")
        ci = chan_index[key]
        ch = cls if cls in scaler["med"] else "__other_med__"
        m, sd = scaler["med"].get(ch, (0.0, 1.0))
        dz = ((math.log1p(dose) - m) / sd) if dose is not None else 0.0
        for t in range(H):
            grid[t][ci] = [dz, 0.0, 1.0, 0.0]; active[t][ci] = 1.0
    return grid, active


def post_grid(e, scaler):
    """Hour-by-hour post-anchor targets: standardized values [POST_H, n_labs] + mask.
    Hour t covers (t, t+1] after the anchor; last measurement in an hour wins.
    Most hours are empty (labs are sparse) -> mask=0 there."""
    vals = [[0.0] * len(TARGET_LABS) for _ in range(POST_H)]
    mask = [[0.0] * len(TARGET_LABS) for _ in range(POST_H)]
    for j, lab in enumerate(TARGET_LABS):
        m, sd = scaler["lab"][lab]
        for (h, v) in sorted(e["post"].get(lab, [])):
            t = int(h)                         # (0,1]->0 ... (71,72]->71
            if 0 <= t < POST_H:
                vals[t][j] = (v - m) / sd; mask[t][j] = 1.0
    return vals, mask


def static_vec(e, scaler):
    m, sd = scaler["age"]
    age = ((e["static"]["age"] - m) / sd) if e["static"]["age"] is not None else 0.0
    return e["static"]["comorbid"] + [age, e["static"]["sex"]]


if __name__ == "__main__":
    tr, va, te, channels, ci, scaler, meta = build()
    print("meta:", meta)
    print("split subjects  train:%d val:%d test(benchmark):%d"
          % (len({e['subject'] for e in tr}), len({e['subject'] for e in va}),
             len({e['subject'] for e in te})))
    # leakage assertion: no subject shared across splits
    st, sv, se = ({e['subject'] for e in tr}, {e['subject'] for e in va}, {e['subject'] for e in te})
    assert not (st & se) and not (sv & se) and not (st & sv), "SUBJECT LEAK across splits!"
    print("leakage check: OK (train/val/test subject-disjoint)")
    print("channels (%d):" % len(channels), [f"{a}:{b}" for a, b in channels[:18]], "...")
    g, act = featurize(tr[0], channels, ci, scaler)
    import numpy as np
    g = np.array(g); act = np.array(act)
    print("grid shape:", g.shape, " active cells:", int(act.sum()))
    print("static dim:", len(static_vec(tr[0], scaler)), " action:", tr[0]["action"])
    print("targets:", tr[0]["targets"], "labels:", tr[0]["labels"])
