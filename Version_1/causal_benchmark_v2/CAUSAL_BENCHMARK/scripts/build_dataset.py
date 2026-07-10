"""
build_dataset.py  —  Two-arm causal episode extraction from MIMIC-IV cardiac data.

Design (confirmed with user):
  ARM A  "pci"      : admission received revascularization (PTCA / stent)
  ARM B  "control"  : cardiac admission with labs, NO revascularization (conservative mgmt)

For each admission we anchor an index time and extract, per cardiac marker, the
measurements in [anchor-WINDOW, anchor] (pre) and (anchor, anchor+WINDOW] (post).
A marker is kept only if it has >=MIN_PRE pre and >=MIN_POST post measurements.
An episode is kept only if >=1 marker survives; pre and post share an identical
marker set by construction (shared_markers).

We also attach a comorbidity vector (from diagnoses) and a per-marker baseline
summary (last pre value, slope, direction) so matched pairs can balance on real
observable confounders.

Output: data/episodes.json  (new nested format)
"""

import pandas as pd
import numpy as np
import json
import logging
from pathlib import Path
from datetime import timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
D = Path("/scratch/users/karun09/physionet.org/files/mimic-iv-ext-cardiac-disease/1.0.0")
BENCH = Path(__file__).parent.parent
OUT = BENCH / "data" / "episodes.json"

LABS_FILE = D / "heart_labevents_examination_group.csv"
PROC_FILE = D / "heart_procedures.csv"
DIAG_FILE = D / "heart_diagnoses_all_true.csv"
NOTES_FILE = D / "heart_diagnoses.csv"            # discharge summaries (use ONLY admission fields)
MICRO_FILE = D / "heart_microbiologyevents.csv"   # cultures, timestamped

# ── Cohort definitions (multiple treated arms vs ONE shared control) ────────
# PCI / percutaneous revascularization
REVASC_CODES = {"0066", "3607", "3606", "0045", "0046", "0047", "027034Z"}
# CABG / surgical revascularization: ICD-9 3611-3619 + ICD-10 coronary bypass 021*
CABG_ICD9 = {"3610", "3611", "3612", "3613", "3614", "3615", "3616", "3617", "3619"}
# NOTE: thrombolysis exists in this dataset in only ~12 admissions — too few for a
# valid matched-pair contrast — so it is intentionally NOT included as an arm.


def arm_for_codes(codes):
    """Assign an admission to ONE treated arm by priority (CABG > PCI), else None.
    Priority keeps arms mutually exclusive when a patient had both procedures."""
    if any(c.startswith("021") or c in CABG_ICD9 for c in codes):
        return "cabg"
    if codes & REVASC_CODES:
        return "pci"
    return None


# PCI sub-grouping by number of vessels treated (ICD-9 00.40 single, 00.41/42/43 multi).
# Multi-vessel PCI manipulates more myocardial territory -> larger troponin release.
PCI_SINGLE_VESSEL = {"0040"}
PCI_MULTI_VESSEL = {"0041", "0042", "0043"}


def pci_vessel_group(codes):
    if codes & PCI_MULTI_VESSEL:
        return "multi"
    if codes & PCI_SINGLE_VESSEL:
        return "single"
    return "unknown"

# Multi-marker design with POSITIVE signals and a NEGATIVE CONTROL.
#   Troponin T, CK-MB  -> positive: PCI mechanically raises them (Type-4a injury).
#   Sodium             -> negative control: tightly regulated, NO direct PCI mechanism,
#                         so a good model should predict ~no differential effect here.
# Scoring is PER MARKER (not pooled), so heterogeneous mechanisms don't muddy one score,
# and the negative control catches models that spuriously "move everything" after PCI.
PRIMARY_MARKER = "Troponin T"          # required anchor; episodes must have it
MARKER_ROLES = {
    "Troponin T": "positive",
    "Creatine Kinase, MB Isoenzyme": "positive",
    "Sodium": "negative_control",
}
CARDIAC_MARKERS = list(MARKER_ROLES.keys())

# ── Task C candidate OUTCOMES (scalar, per-episode) ─────────────────────────
# Only lab-derived outcomes are available in this MIMIC-IV cardiac-ext subset
# (no admissions/patients/icustays tables -> no mortality / ICU-LOS / demographics).
# Each candidate is computed over (0, OUTCOME_WINDOW_H] after the index time. The
# automated selector (select_outcome.py) scores these and picks the primary Y.
OUTCOME_WINDOW_H = 72
OUTCOME_SPECS = {
    # key                     label (in labevents)                    aggregation
    "peak_troponin_72h":     {"label": "Troponin T",                       "agg": "peak"},
    "peak_ckmb_72h":         {"label": "Creatine Kinase, MB Isoenzyme",    "agg": "peak"},
    "peak_lactate_72h":      {"label": "Lactate",                          "agg": "peak"},
    "delta_creatinine_72h":  {"label": "Creatinine",                       "agg": "delta"},
}

# Comorbidity groups keyed by ICD-10 prefix (for matching / balance)
COMORBIDITIES = {
    "diabetes": ("E10", "E11"),
    "hypertension": ("I10", "I11", "I12", "I13"),
    "ckd": ("N18", "N17"),
    "heart_failure": ("I50",),
    "afib": ("I48",),
    "prior_mi": ("I21", "I22", "I252"),
    "hyperlipidemia": ("E78",),
    "copd": ("J44",),
    "cad": ("I25",),
    "valve": ("I34", "I35"),
}

# ── Extraction parameters ──────────────────────────────────────────────────
WINDOW_H = 96
MIN_PRE = 2
MIN_POST = 1
MAX_PER_ARM = 100000  # effectively unbounded

# Control-arm index time = first troponin draw + this offset (the cardiac-presentation
# workup as a fixed, event-grounded time-zero). This replaces the old lab-span MIDPOINT
# anchor, which was outcome-dependent (longer monitoring -> later index -> prognosis leak).
CONTROL_INDEX_OFFSET_H = 24


def classify_treated(procs):
    """Return (arm_of_admission, anchors_by_arm).
    arm_of: {hadm_id: 'pci'|'cabg'}.  anchors_by_arm: {arm: Series hadm_id->first proc datetime}."""
    procs["code"] = procs["icd_code"].astype(str)
    by_adm = procs.groupby("hadm_id")["code"].apply(set)
    arm_of = {}
    for h, codes in by_adm.items():
        arm = arm_for_codes(codes)
        if arm:
            arm_of[h] = arm

    def is_cabg(c):
        return c.startswith("021") or c in CABG_ICD9
    anchors = {
        "cabg": procs[procs["code"].apply(is_cabg)].groupby("hadm_id")["chartdate"].min(),
        "pci": procs[procs["code"].isin(REVASC_CODES)].groupby("hadm_id")["chartdate"].min(),
    }
    return arm_of, anchors


def pre_trend(values, hours):
    """Return (last_pre_value, slope_per_h, direction) from pre measurements."""
    if len(values) == 1:
        return values[0], 0.0, "stable"
    x = np.array(hours, float)
    y = np.array(values, float)
    if x.max() == x.min():
        return y[-1], 0.0, "stable"
    slope = float(np.polyfit(x, y, 1)[0])
    direction = "stable" if abs(slope) < 1e-4 else ("rising" if slope > 0 else "falling")
    return float(y[-1]), round(slope, 5), direction


def extract_marker_windows(marker_df, anchor):
    """marker_df: rows for one admission. Returns (pre, post) dicts of marker->list[{value,hours}]."""
    pre, post = {}, {}
    for label, md in marker_df.groupby("label"):
        dt = (md["charttime"] - anchor).dt.total_seconds() / 3600.0
        pre_mask = (dt <= 0)                       # NO before-window: everything up to the index
        post_mask = (dt > 0) & (dt <= WINDOW_H)    # 96h prediction target after the index
        pre_vals = [{"value": float(v), "hours_from_index": round(float(h), 2)}
                    for v, h in zip(md["valuenum"][pre_mask], dt[pre_mask])]
        post_vals = [{"value": float(v), "hours_from_index": round(float(h), 2)}
                     for v, h in zip(md["valuenum"][post_mask], dt[post_mask])]
        if len(pre_vals) >= MIN_PRE and len(post_vals) >= MIN_POST:
            pre_vals.sort(key=lambda r: r["hours_from_index"])
            post_vals.sort(key=lambda r: r["hours_from_index"])
            pre[label] = pre_vals
            post[label] = post_vals
    return pre, post


def build_comorbidity_vector(codes):
    vec = {k: 0 for k in COMORBIDITIES}
    for code in codes:
        c = str(code)
        for name, prefixes in COMORBIDITIES.items():
            if any(c.startswith(p) for p in prefixes):
                vec[name] = 1
    return vec


def _clip(text, n=1500):
    t = str(text).strip()
    return t[:n] + (" …[truncated]" if len(t) > n else "")


def summarize_all_labs(adm_labs, anchor):
    """ALL labs up to the index time -> per-lab compact summary (first/latest/min/max)."""
    out = {}
    if adm_labs is None or len(adm_labs) == 0:
        return out
    pre = adm_labs[adm_labs["charttime"] <= anchor]
    for label, md in pre.groupby("label"):
        md = md.sort_values("charttime")
        vals = [float(v) for v in md["valuenum"].tolist()]
        if not vals:
            continue
        unit = ""
        if "valueuom" in md and pd.notna(md["valueuom"].iloc[-1]):
            unit = str(md["valueuom"].iloc[-1])
        out[str(label)] = {"n": len(vals), "first": round(vals[0], 3), "latest": round(vals[-1], 3),
                           "min": round(min(vals), 3), "max": round(max(vals), 3), "unit": unit}
    return out


def pre_labs_full(adm_labs_all, anchor):
    """FULL timestamped pre-index series for EVERY lab (charttime <= index). No summary —
    the model sees each draw. Rendered with a token cap at prompt-build time, not here."""
    out = {}
    if adm_labs_all is None or len(adm_labs_all) == 0:
        return out
    pre = adm_labs_all[adm_labs_all["charttime"] <= anchor]
    for label, md in pre.groupby("label"):
        md = md.sort_values("charttime")
        series = [{"value": round(float(v), 3),
                   "hours_from_index": round((t - anchor).total_seconds() / 3600.0, 1)}
                  for v, t in zip(md["valuenum"], md["charttime"]) if pd.notna(v)]
        if series:
            out[str(label)] = series
    return out


def summarize_micro(adm_micro, anchor, cap=40):
    """Microbiology events up to the index time."""
    out = []
    if adm_micro is None or len(adm_micro) == 0:
        return out
    pre = adm_micro[adm_micro["charttime"] <= anchor].sort_values("charttime")
    for _, r in pre.iterrows():
        org = r.get("org_name")
        interp = r.get("interpretation")
        out.append({
            "hours_from_index": round((r["charttime"] - anchor).total_seconds() / 3600.0, 1),
            "specimen": str(r.get("spec_type_desc", "") or ""),
            "test": str(r.get("test_name", "") or ""),
            "organism": str(org) if pd.notna(org) else "",
            "interpretation": str(interp) if pd.notna(interp) else "",
        })
    return out[:cap]


def extract_outcomes(adm_labs_all, anchor):
    """Scalar candidate outcomes over (0, OUTCOME_WINDOW_H] after the index time.
    Uses the full per-admission lab frame (creatinine/lactate are not cardiac markers,
    so they live in labs_all, not the scoring subset). Each outcome carries a `missing`
    flag so the selector can score completeness honestly.
      - peak  : max post-index value within the window.
      - delta : (max post-index value) − (last value at/before the index), i.e. the
                72h rise relative to the patient's own pre-index baseline (e.g. AKI).
    """
    out = {}
    if adm_labs_all is None or len(adm_labs_all) == 0:
        return {k: {"value": None, "n_post": 0, "missing": True} for k in OUTCOME_SPECS}
    for key, spec in OUTCOME_SPECS.items():
        sub = adm_labs_all[adm_labs_all["label"] == spec["label"]].sort_values("charttime")
        if len(sub) == 0:
            out[key] = {"value": None, "n_post": 0, "missing": True}
            continue
        d = (sub["charttime"] - anchor).dt.total_seconds() / 3600.0
        post = sub["valuenum"][(d > 0) & (d <= OUTCOME_WINDOW_H)]
        n_post = int(len(post))
        if n_post == 0:
            out[key] = {"value": None, "n_post": 0, "missing": True}
            continue
        peak_post = float(np.nanmax(post.values))
        if spec["agg"] == "peak":
            out[key] = {"value": round(peak_post, 4), "n_post": n_post, "missing": False}
        else:  # delta vs the patient's last pre-index baseline
            pre = sub["valuenum"][d <= 0]
            if len(pre) == 0:
                out[key] = {"value": None, "n_post": n_post, "missing": True, "note": "no_pre_baseline"}
                continue
            baseline = float(pre.iloc[-1])
            out[key] = {"value": round(peak_post - baseline, 4), "n_post": n_post,
                        "baseline": round(baseline, 4), "peak_post": round(peak_post, 4),
                        "missing": False}
    return out


def make_episode(eid, hadm_id, arm, anchor, pre, post, comorbid, clinical_context, outcomes):
    markers = list(pre.keys())          # markers meeting density in BOTH pre and post
    baseline = {}
    for m in markers:
        vals = [r["value"] for r in pre[m]]
        hrs = [r["hours_from_index"] for r in pre[m]]
        last, slope, direction = pre_trend(vals, hrs)
        baseline[m] = {"last_pre_value": last, "slope_per_h": slope, "direction": direction,
                       "n_pre": len(vals)}
    return {
        "episode_id": eid,
        "hadm_id": int(hadm_id),
        "intervention": {"type": arm, "index_time": anchor.isoformat()},
        "primary_marker": PRIMARY_MARKER,
        "markers_present": markers,
        "marker_roles": {m: MARKER_ROLES[m] for m in markers},
        # Full pre-intervention CHART context shown to the model (safe fields only):
        "clinical_context": clinical_context,
        "pre_context": {
            "window_hours": WINDOW_H,
            "markers": pre,
            "measurement_density": {m: len(pre[m]) for m in markers},
        },
        "post_trajectory": {
            "window_hours": WINDOW_H,
            "markers": post,
            "measurement_density": {m: len(post[m]) for m in markers},
        },
        "baseline_summary": baseline,
        "comorbidities": comorbid,
        "n_comorbidities": int(sum(comorbid.values())),
        # Task C scalar candidate outcomes over (0, OUTCOME_WINDOW_H] post-index.
        "outcomes": outcomes,
    }


def main():
    log.info("Loading procedures, labs, diagnoses ...")
    procs = pd.read_csv(PROC_FILE)
    procs["chartdate"] = pd.to_datetime(procs["chartdate"]) + timedelta(hours=12)  # split the day

    # ALL labs (for full-chart context); cardiac subset (for scoring) derived from it.
    labs_all = pd.read_csv(LABS_FILE, low_memory=False,
                           usecols=["hadm_id", "charttime", "valuenum", "valueuom", "label"])
    labs_all["charttime"] = pd.to_datetime(labs_all["charttime"])
    labs_all = labs_all[labs_all["valuenum"].notna()]
    labs = labs_all[labs_all["label"].isin(CARDIAC_MARKERS)]

    diag = pd.read_csv(DIAG_FILE, usecols=["hadm_id", "icd_code"])
    diag_by_adm = diag.groupby("hadm_id")["icd_code"].apply(list).to_dict()

    # Microbiology (timestamped -> filterable to pre-intervention)
    log.info("Loading microbiology + admission notes ...")
    micro = pd.read_csv(MICRO_FILE, low_memory=False,
                        usecols=["hadm_id", "charttime", "chartdate", "spec_type_desc",
                                 "test_name", "org_name", "interpretation"])
    micro["charttime"] = pd.to_datetime(micro["charttime"].fillna(micro["chartdate"]), errors="coerce")
    micro = micro[micro["charttime"].notna()]

    # Admission presentation notes (SAFE pre-intervention fields only). The file is a
    # discharge summary, but HPI / admission physical_exam / chief_complaint describe presentation.
    notes = pd.read_csv(NOTES_FILE, low_memory=False,
                        usecols=["hadm_id", "HPI", "physical_exam", "chief_complaint"])
    notes_by_adm = {int(r["hadm_id"]): {
        "chief_complaint": _clip(r.get("chief_complaint", ""), 300),
        "hpi": _clip(r.get("HPI", ""), 1800),
        "physical_exam": _clip(r.get("physical_exam", ""), 1800),
    } for _, r in notes.iterrows() if pd.notna(r["hadm_id"])}

    arm_of, treated_anchors = classify_treated(procs)
    # vessel group per admission (procs["code"] set inside classify_treated)
    codes_by_adm = procs.groupby("hadm_id")["code"].apply(set)
    vessel_of = {h: pci_vessel_group(c) for h, c in codes_by_adm.items()}
    adm_with_labs = set(labs["hadm_id"].unique())
    treated_sets = {
        "cabg": {h for h, a in arm_of.items() if a == "cabg"},
        "pci": {h for h, a in arm_of.items() if a == "pci"},
    }
    # Control = cardiac admission with labs and NO active intervention of any arm.
    control_set = adm_with_labs - set(arm_of)

    # Control index = first TROPONIN draw + fixed offset (event-grounded, NOT outcome-dependent).
    trop_labs = labs[labs["label"] == PRIMARY_MARKER]
    first_trop = trop_labs.groupby("hadm_id")["charttime"].min()
    control_anchor = first_trop + timedelta(hours=CONTROL_INDEX_OFFSET_H)

    labs_by_adm = dict(tuple(labs.groupby("hadm_id")))

    # Per-admission groupings for full-chart context, limited to relevant admissions (memory).
    relevant = treated_sets["cabg"] | treated_sets["pci"] | control_set
    all_labs_by_adm = dict(tuple(labs_all[labs_all["hadm_id"].isin(relevant)].groupby("hadm_id")))
    micro_by_adm = dict(tuple(micro[micro["hadm_id"].isin(relevant)].groupby("hadm_id")))

    episodes = []
    counts = {"pci": 0, "cabg": 0, "control": 0}

    def process(adms, arm, anchor_map):
        n_skip = 0
        for h in adms:
            if counts[arm] >= MAX_PER_ARM:
                break
            a = anchor_map.get(h)
            if a is None or h not in labs_by_adm:
                n_skip += 1
                continue
            pre, post = extract_marker_windows(labs_by_adm[h], a)
            # Require the PRIMARY marker (troponin) with density; others are optional extras.
            if PRIMARY_MARKER not in pre:
                n_skip += 1
                continue
            comorbid = build_comorbidity_vector(diag_by_adm.get(h, []))
            adm_all = all_labs_by_adm.get(h)
            # Full pre-intervention chart context (safe fields only)
            clinical_context = {
                **notes_by_adm.get(int(h), {"chief_complaint": "", "hpi": "", "physical_exam": ""}),
                "labs_all": summarize_all_labs(adm_all, a),     # compact summary (fallback / severity)
                "labs_full": pre_labs_full(adm_all, a),          # FULL timestamped pre-index series
                "microbiology": summarize_micro(micro_by_adm.get(h), a),
            }
            outcomes = extract_outcomes(adm_all, a)
            eid = f"ep_{arm}_{counts[arm]:05d}"
            ep = make_episode(eid, h, arm, a, pre, post, comorbid, clinical_context, outcomes)
            if arm == "pci":
                ep["pci_vessels"] = vessel_of.get(h, "unknown")
            episodes.append(ep)
            counts[arm] += 1
        log.info(f"  arm {arm}: kept {counts[arm]}, skipped {n_skip}")

    log.info(f"Candidates -> cabg:{len(treated_sets['cabg'])} pci:{len(treated_sets['pci'])} control:{len(control_set)}")
    process(sorted(treated_sets["cabg"]), "cabg", treated_anchors["cabg"])
    process(sorted(treated_sets["pci"]), "pci", treated_anchors["pci"])
    process(sorted(control_set), "control", control_anchor)

    # per-marker availability (how many episodes have each marker scorable)
    avail = {m: 0 for m in CARDIAC_MARKERS}
    for e in episodes:
        for m in e["markers_present"]:
            avail[m] += 1
    log.info(f"Total episodes: {len(episodes)}  (cabg={counts['cabg']}, pci={counts['pci']}, control={counts['control']})")
    log.info(f"Per-marker availability: {avail}")

    # Per-outcome, per-arm completeness (how the selector will judge criterion (a))
    outcome_availability = {}
    for key in OUTCOME_SPECS:
        per_arm = {}
        for arm in ("pci", "control", "cabg"):
            eps = [e for e in episodes if e["intervention"]["type"] == arm]
            if not eps:
                continue
            present = sum(1 for e in eps if not e["outcomes"].get(key, {}).get("missing", True))
            per_arm[arm] = {"present": present, "n": len(eps),
                            "complete_frac": round(present / len(eps), 3)}
        outcome_availability[key] = per_arm
    log.info(f"Per-outcome completeness by arm: {outcome_availability}")

    OUT.write_text(json.dumps({
        "benchmark": "causal_intervention_episodes_mimic_multiarm_v6",
        "control_index": f"first_troponin + {CONTROL_INDEX_OFFSET_H}h (event-grounded)",
        "n_episodes": len(episodes),
        "arms": {"cabg": counts["cabg"], "pci": counts["pci"], "control": counts["control"]},
        "treated_arms": ["pci", "cabg"],
        "primary_marker": PRIMARY_MARKER,
        "marker_roles": MARKER_ROLES,
        "marker_availability": avail,
        "outcome_window_hours": OUTCOME_WINDOW_H,
        "candidate_outcomes": list(OUTCOME_SPECS.keys()),
        "outcome_availability": outcome_availability,
        "window_hours": WINDOW_H,
        "min_pre": MIN_PRE, "min_post": MIN_POST,
        "episodes": episodes,
    }, indent=2))
    log.info(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
