#!/usr/bin/env python3
"""
Longitudinal context builder — one patient, four time-ordered steps A -> C -> B -> A2.

Reads the cohort slices produced by cohort.py and, for each ICU stay, computes the
DATA-DERIVED spine of a longitudinal case anchored on its lab-driven intervention P
(at time tP). No models — this is the ground-truth structure the generation agents
later turn into questions.

Steps (mirror the standalone benchmarks, chained on the SAME patient):
  A1  next-intervention : time-zero = ICU intime; requestable labs are pre-tP; the answer
                          is P's family (dialysis/transfusion/ventilation); golden = the
                          ABNORMAL decisive lab for that family.
  C   counterfactual ID : P actually happened; present P vs a plausible ALTERNATIVE family;
                          observed post-panel = core labs after tP; answer = the real family.
  B   trajectory        : given P at tP, per-core-lab direction over 72h (ref-range rule).
  A2  downstream outcome: time-zero = dischtime; label = mortality_1y and readmission_30d.

Run:  python context_builder.py   (writes longitudinal_contexts.json)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "cohort_data"
POST_H = 72
STABLE_FRAC = 0.25

# decisive labs + expected post-effect per intervention family (for A golden + C discrimination)
FAMILY_LABS = {
    "dialysis":   {"Creatinine": "down", "Potassium": "down", "Urea Nitrogen": "down"},
    "transfusion": {"Hemoglobin": "up", "Hematocrit": "up"},
    "ventilation": {"pCO2": "down", "pH": "up", "pO2": "up"},
}
ALT_FAMILY = {"dialysis": "transfusion", "transfusion": "dialysis", "ventilation": "dialysis"}


def _dt(s):
    return pd.to_datetime(s, errors="coerce")


class Cohort:
    def __init__(self):
        self.idx = json.load(open(DATA / "cohort_index.json"))
        self.labs = pd.read_parquet(DATA / "labs.parquet")
        self.labs["charttime"] = _dt(self.labs["charttime"])
        dl = pd.read_parquet(DATA / "d_labitems.parquet")
        self.lab_name = dict(zip(dl["itemid"], dl["label"]))
        self.adm = pd.read_parquet(DATA / "admissions.parquet")
        for c in ("admittime", "dischtime", "deathtime"):
            self.adm[c] = _dt(self.adm[c])
        self.pat = pd.read_parquet(DATA / "patients.parquet")
        dx = pd.read_parquet(DATA / "diagnoses_icd.parquet")
        dxt = pd.read_parquet(DATA / "d_icd_diagnoses.parquet")
        self.dx_title = dict(zip(zip(dxt["icd_code"], dxt["icd_version"]), dxt["long_title"]))
        self.dx = dx
        self._labs_by = {h: g for h, g in self.labs.groupby("hadm_id")}

    def _named(self, df):
        df = df.copy(); df["lab"] = df["itemid"].map(self.lab_name); return df

    def _core_labs(self, hadm_id, t0):
        L = self._labs_by.get(hadm_id)
        if L is None:
            return []
        L = self._named(L)
        hi = t0 + pd.Timedelta(hours=POST_H)
        pre = L[(L["charttime"] < t0) & L["valuenum"].notna()]
        post = L[(L["charttime"] > t0) & (L["charttime"] <= hi) & L["valuenum"].notna()]
        out = []
        for lab in set(pre["lab"]).intersection(post["lab"]):
            pr = pre[pre["lab"] == lab].sort_values("charttime")
            po = post[post["lab"] == lab].sort_values("charttime")
            if len(pr) < 2 or len(po) < 2:
                continue
            rl, rh = pr.iloc[-1]["ref_range_lower"], pr.iloc[-1]["ref_range_upper"]
            try:
                rl, rh = float(rl), float(rh)
            except (TypeError, ValueError):
                continue
            if not (rh - rl > 0):
                continue
            pv, sv = float(pr.iloc[-1]["valuenum"]), float(po.iloc[-1]["valuenum"])
            d = sv - pv
            band = STABLE_FRAC * (rh - rl)
            direction = "Stable" if abs(d) <= band else ("Rising" if d > 0 else "Falling")
            out.append({"lab": str(lab), "ref_low": rl, "ref_high": rh,
                        "pre_value": pv, "post_value": sv, "direction": direction,
                        "abnormal_pre": pv < rl or pv > rh})
        return out

    def _pre_labs(self, hadm_id, t0):
        L = self._labs_by.get(hadm_id)
        if L is None:
            return []
        L = self._named(L)
        pre = L[L["charttime"] < t0]
        return [{"lab": str(r["lab"]), "value": r["value"], "valuenum": r["valuenum"],
                 "unit": r["valueuom"], "flag": r["flag"], "charttime": str(r["charttime"])}
                for _, r in pre.iterrows()]

    def _dx_history(self, hadm_id):
        d = self.dx[self.dx["hadm_id"] == hadm_id]
        return [self.dx_title.get((r["icd_code"], r["icd_version"]), str(r["icd_code"]))
                for _, r in d.iterrows()][:15]

    def _a2_outcome(self, subject_id, hadm_id):
        a = self.adm[self.adm["hadm_id"] == hadm_id]
        if not len(a):
            return {"dischtime": None, "mortality_1y": None, "readmission_30d": None}
        disch = a.iloc[0]["dischtime"]
        prow = self.pat[self.pat["subject_id"] == subject_id]
        dod = _dt(pd.Series([prow.iloc[0]["dod"]]))[0] if len(prow) and pd.notna(prow.iloc[0].get("dod")) else pd.NaT
        mort = bool(pd.notna(dod) and pd.notna(disch) and 0 <= (dod - disch).days <= 365)
        subj_adm = self.adm[self.adm["subject_id"] == subject_id].sort_values("admittime")
        future = subj_adm[subj_adm["admittime"] > disch] if pd.notna(disch) else subj_adm.iloc[0:0]
        readm = bool(len(future) and (future["admittime"].min() - disch).days <= 30)
        return {"dischtime": str(disch), "mortality_1y": mort, "readmission_30d": readm}

    def build(self, p) -> dict:
        hadm, subj = p["hadm_id"], p["subject_id"]
        tP = pd.to_datetime(p["anchor_time"]); intime = pd.to_datetime(p["icu_intime"])
        fam = p["anchor_family"]
        core = self._core_labs(hadm, tP)
        core_names = {c["lab"] for c in core}
        # A1 golden: decisive family lab that is abnormal pre-tP (fall back to any abnormal core)
        fam_labs = FAMILY_LABS.get(fam, {})
        golden = [c for c in core if c["abnormal_pre"]
                  and any(fl.lower() in c["lab"].lower() for fl in fam_labs)]
        if not golden:
            golden = [c for c in core if c["abnormal_pre"]][:1]
        alt = ALT_FAMILY.get(fam, "dialysis")
        return {
            "subject_id": subj, "hadm_id": hadm, "stay_id": p["stay_id"],
            "demographics": self._demo(subj, hadm),
            "dx_history": self._dx_history(hadm),
            "anchor": {"family": fam, "procedure": p["anchor_procedure"], "time": str(tP)},
            "A1_next_intervention": {
                "time_zero": str(intime), "answer_family": fam,
                "distractor_families": [f for f in FAMILY_LABS if f != fam],
                "golden_labs": [{"lab": g["lab"], "pre_value": g["pre_value"],
                                 "ref_low": g["ref_low"], "ref_high": g["ref_high"]} for g in golden],
                "pre_labs_available": len(self._pre_labs(hadm, tP))},
            # C is attached in main() via cross-patient pairing (two REAL patients)
            "C_attribution": None,
            "_core": core,
            "B_trajectory": {
                "targets": [{"lab": c["lab"], "ref_low": c["ref_low"], "ref_high": c["ref_high"],
                             "pre_value": c["pre_value"], "direction": c["direction"]} for c in core]},
            "A2_outcome": self._a2_outcome(subj, hadm),
            "_n_core_labs": len(core),
        }

    def _demo(self, subj, hadm):
        prow = self.pat[self.pat["subject_id"] == subj]
        a = self.adm[self.adm["hadm_id"] == hadm]
        return {"gender": str(prow.iloc[0]["gender"]) if len(prow) else None,
                "anchor_age": int(prow.iloc[0]["anchor_age"]) if len(prow) else None,
                "admission_type": str(a.iloc[0]["admission_type"]) if len(a) else None,
                "race": str(a.iloc[0]["race"]) if len(a) else None}


MAX_PRESTATE_DIST = 0.75
MIN_SHARED = 3


def _zmap(core):
    """lab -> z of pre-value relative to reference-range center."""
    z = {}
    for c in core:
        half = (c["ref_high"] - c["ref_low"]) / 2.0
        if half > 0:
            z[c["lab"]] = (c["pre_value"] - (c["ref_low"] + c["ref_high"]) / 2.0) / half
    return z


def _pair(a, b):
    """(distance, shared_labs) for two patient contexts, or (None, []) if incompatible."""
    za, zb = _zmap(a["_core"]), _zmap(b["_core"])
    shared = sorted(set(za) & set(zb))
    if len(shared) < MIN_SHARED:
        return None, []
    d = sum(abs(za[l] - zb[l]) for l in shared) / len(shared)
    return d, shared


def _attach_C(contexts):
    """Pair each patient with a REAL cohort partner of a DIFFERENT anchor family + similar
    baseline; build the two-real-patient attribution. Greedy, each unused patient once."""
    used = set()
    n_paired = 0
    for i, a in enumerate(contexts):
        if i in used:
            continue
        best = None
        for j, b in enumerate(contexts):
            if j == i or j in used or b["anchor"]["family"] == a["anchor"]["family"]:
                continue
            d, shared = _pair(a, b)
            if d is not None and d <= MAX_PRESTATE_DIST and (best is None or d < best[0]):
                best = (d, j, b, shared)
        if not best:
            continue
        d, j, b, shared = best
        used.add(i); used.add(j)
        answer = "A" if n_paired % 2 == 0 else "B"          # balanced ground truth
        winner = a if answer == "A" else b
        wcore = {c["lab"]: c for c in winner["_core"]}
        observed = [{"lab": l, "value": wcore[l]["post_value"]} for l in shared if l in wcore]

        def pt(x):
            return {"subject_id": x["subject_id"], "hadm_id": x["hadm_id"],
                    "procedure_family": x["anchor"]["family"], "procedure": x["anchor"]["procedure"],
                    "pre_labs": [{"lab": c["lab"], "value": c["pre_value"]}
                                 for c in x["_core"] if c["lab"] in shared]}
        cattr = {"patient_A": pt(a), "patient_B": pt(b), "shared_labs": shared,
                 "observed_post": observed, "answer": answer,
                 "pre_state_distance": round(d, 3)}
        a["C_attribution"] = cattr
        b["C_attribution"] = {**cattr, "_note": "same pair, from partner's perspective"}
        n_paired += 1
    return n_paired


def main():
    ch = Cohort()
    contexts = [ch.build(p) for p in ch.idx["patients"]]
    n_pairs = _attach_C(contexts)
    for c in contexts:                                       # drop internal helper field
        c.pop("_core", None)
    json.dump({"cohort_size": len(contexts), "sequence": ["A1", "C", "B", "A2"],
               "c_pairs": n_pairs, "contexts": contexts},
              open(HERE / "longitudinal_contexts.json", "w"), indent=2, default=str)
    from collections import Counter
    print(f"built {len(contexts)} longitudinal contexts -> longitudinal_contexts.json")
    print("anchor families:", dict(Counter(c["anchor"]["family"] for c in contexts)))
    print("avg core labs:", round(sum(c["_n_core_labs"] for c in contexts) / max(len(contexts), 1), 1))
    print(f"C two-real-patient pairs formed: {n_pairs}  (patients with a C question: {n_pairs*2})")
    print("A2 mortality_1y positives:", sum(1 for c in contexts if c["A2_outcome"]["mortality_1y"]))


if __name__ == "__main__":
    main()
