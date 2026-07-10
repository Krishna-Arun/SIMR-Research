"""Benchmark C per-pair context.

build_context(pair_uid) -> both patients' pre-procedure state (core labs + comorbidities + procedure)
plus ONE patient's post-procedure core labs (the shown_post_owner). Ground truth = which patient
(A/B) the post-state belongs to. Reuses Benchmark B's core_labs scan via cohort.reuse_from.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from qgen.config import mimic_root, out_dir
from qgen.mimic_features import build_comorbidity_vector


class ContextStore:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.root = mimic_root(cfg)
        od = out_dir(cfg)
        self.src = Path(cfg["cohort"]["reuse_from"])
        self.win = float(cfg["cohort"]["post_window_h"])
        self.core = list(cfg["cohort"]["core_labs"])
        self.pairs = pd.read_parquet(od / "matched_pairs.parquet").set_index("pair_uid")
        self.pool = list(self.pairs.index)
        self.eindex = pd.read_parquet(self.src / "eligible_index.parquet").set_index("proc_uid")
        self.core_labs_path = self.src / "core_labs.parquet"
        self._patients = None
        self._diag = None
        self._labs_by = None

    def _gz(self, subdir, table):
        p = self.root / subdir / f"{table}.csv.gz"
        return p if p.exists() else self.root / subdir / f"{table}.csv"

    @property
    def patients(self):
        if self._patients is None:
            self._patients = pd.read_csv(self._gz("hosp", "patients"),
                                         usecols=["subject_id", "gender", "anchor_age"]).set_index("subject_id")
        return self._patients

    @property
    def diag(self):
        if self._diag is None:
            self._diag = pd.read_csv(self._gz("hosp", "diagnoses_icd"), usecols=["hadm_id", "icd_code"])
        return self._diag

    def _labs(self, hadm_id):
        if self._labs_by is None:                      # load once, group by hadm
            d = pd.read_parquet(self.core_labs_path)
            d["charttime"] = pd.to_datetime(d["charttime"], errors="coerce")
            self._labs_by = {h: g for h, g in d.groupby("hadm_id")}
        return self._labs_by.get(hadm_id, pd.DataFrame())

    def _patient_block(self, proc_uid, with_post: bool):
        row = self.eindex.loc[proc_uid]
        hadm = int(row["hadm_id"]); subj = int(row["subject_id"])
        start = pd.to_datetime(row["starttime"])
        labs = self._labs(hadm)
        pre, post = {}, {}
        if len(labs):
            for label, g in labs.groupby("label"):
                g = g.sort_values("charttime")
                dt = (g["charttime"] - start).dt.total_seconds() / 3600.0
                gp = g[dt <= 0]; gq = g[(dt > 0) & (dt <= self.win)]
                if len(gp):
                    pre[str(label)] = {"latest": round(float(gp["valuenum"].iloc[-1]), 3), "n": int(len(gp))}
                if with_post and len(gq):
                    post[str(label)] = [{"value": round(float(v), 3),
                                         "h": round(float((t - start).total_seconds() / 3600.0), 1)}
                                        for v, t in zip(gq["valuenum"], gq["charttime"]) if pd.notna(v)]
        demo = {"hadm_id": hadm, "subject_id": subj}
        if subj in self.patients.index:
            p = self.patients.loc[subj]
            demo.update(gender=str(p["gender"]), anchor_age=int(p["anchor_age"]))
        dcodes = self.diag[self.diag["hadm_id"] == hadm]["icd_code"].astype(str).tolist()
        comorbid = {k: v for k, v in build_comorbidity_vector(dcodes).items() if v}
        block = {"procedure": str(row["proc_label"]), "demographics": demo,
                 "comorbidities": comorbid, "pre_labs": pre}
        if with_post:
            block["post_labs"] = post
        return block

    def build_context(self, pair_uid: str) -> dict:
        pr = self.pairs.loc[pair_uid]
        owner = str(pr["shown_post_owner"])           # "A" or "B" (ground truth)
        A = self._patient_block(pr["proc_uidA"], with_post=(owner == "A"))
        B = self._patient_block(pr["proc_uidB"], with_post=(owner == "B"))
        shown_post = (A if owner == "A" else B).pop("post_labs", {})
        return {
            "pair_uid": pair_uid,
            "patient_A": A, "patient_B": B,
            "procA": str(pr["procA"]), "procB": str(pr["procB"]),
            "shown_post_labs": shown_post,            # unlabeled — from the owner patient
            "shown_post_owner": owner,                # GROUND TRUTH
            "match_quality": {"pA": float(pr["pA"]), "pB": float(pr["pB"])},
            "hadm_id": int(A["demographics"]["hadm_id"]),     # for resume bookkeeping
            "subject_id": int(A["demographics"]["subject_id"]),
        }


if __name__ == "__main__":
    import json, sys
    from qgen.config import load_config
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    s = ContextStore(cfg)
    ctx = s.build_context(sys.argv[2] if len(sys.argv) > 2 else s.pool[0])
    print(json.dumps(ctx, indent=2, default=str)[:2500])
