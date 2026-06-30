"""Benchmark B per-procedure context + ground-truth trajectories.

build_context(proc_uid) -> dict with the index ICU procedure, pre-procedure core-lab summary,
prior procedures ("invasions"), diagnoses, comorbidities, demographics, and the DETERMINISTIC
post-procedure trajectory labels (from qgen.trajectory). The optimizer writes the question + causal
justification; the directions themselves are data-derived ground truth.
"""
from __future__ import annotations

import pandas as pd

from qgen.config import mimic_root, out_dir
from qgen.mimic_features import build_comorbidity_vector, summarize_meds, summarize_micro
from qgen.trajectory import trajectories_for_procedure


class ContextStore:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.root = mimic_root(cfg)
        od = out_dir(cfg)
        self.win = float(cfg["cohort"]["post_window_h"])
        self.min_pre = int(cfg["cohort"]["min_pre"])
        self.min_post = int(cfg["cohort"]["min_post"])
        self.core_labs_path = od / "core_labs.parquet"
        self.micro_path = od / "micro.parquet"
        self.meds_path = od / "meds.parquet"
        self.index = pd.read_parquet(od / "eligible_index.parquet").set_index("proc_uid")
        pool_path = od / "pool.parquet"
        self.pool = (pd.read_parquet(pool_path)["proc_uid"].tolist()
                     if pool_path.exists() else list(self.index.index))
        self.procedures = pd.read_parquet(od / "procedures.parquet")
        self._patients = None
        self._adm = None
        self._diag = None
        self._labs_by = None
        self._micro_by = None
        self._meds_by = None

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
            self._diag = pd.read_csv(self._gz("hosp", "diagnoses_icd"),
                                     usecols=["hadm_id", "icd_code", "seq_num"]).sort_values("seq_num")
        return self._diag

    def _core_labs(self, hadm_id: int) -> pd.DataFrame:
        if self._labs_by is None:                      # load once, group by hadm (fast per-item access)
            d = pd.read_parquet(self.core_labs_path)
            d["charttime"] = pd.to_datetime(d["charttime"], errors="coerce")
            self._labs_by = {h: g for h, g in d.groupby("hadm_id")}
        return self._labs_by.get(hadm_id, pd.DataFrame())

    def _aux(self, hadm_id: int, kind: str):
        """Per-hadm microbiology / medication slice (loaded once, grouped by hadm)."""
        if kind == "micro" and self._micro_by is None:
            m = pd.read_parquet(self.micro_path) if self.micro_path.exists() else None
            if m is not None and "charttime" in m:
                m["charttime"] = pd.to_datetime(m["charttime"], errors="coerce")
            self._micro_by = {h: g for h, g in m.groupby("hadm_id")} if m is not None else {}
        if kind == "meds" and self._meds_by is None:
            d = pd.read_parquet(self.meds_path) if self.meds_path.exists() else None
            if d is not None and "starttime" in d:
                d["starttime"] = pd.to_datetime(d["starttime"], errors="coerce")
            self._meds_by = {h: g for h, g in d.groupby("hadm_id")} if d is not None else {}
        return (self._micro_by if kind == "micro" else self._meds_by).get(hadm_id)

    def build_context(self, proc_uid: str) -> dict:
        row = self.index.loc[proc_uid]
        hadm_id = int(row["hadm_id"]); subject_id = int(row["subject_id"])
        start = pd.to_datetime(row["starttime"])

        labs = self._core_labs(hadm_id)
        micro = self._aux(hadm_id, "micro")
        meds = self._aux(hadm_id, "meds")
        trajs = trajectories_for_procedure(labs, start, self.win, self.min_pre, self.min_post)

        # pre-procedure core-lab summary (values before time-zero)
        pre_summary = {}
        if len(labs):
            pre = labs[labs["charttime"] <= start]
            for label, g in pre.groupby("label"):
                g = g.sort_values("charttime")
                vals = [float(v) for v in g["valuenum"] if pd.notna(v)]
                if vals:
                    pre_summary[str(label)] = {"latest": round(vals[-1], 3), "n": len(vals),
                                               "min": round(min(vals), 3), "max": round(max(vals), 3)}

        # prior procedures within the admission, before the index procedure ("invasions")
        pr = self.procedures[(self.procedures["hadm_id"] == hadm_id) &
                             (pd.to_datetime(self.procedures["starttime"]) < start)]
        prior = sorted(set(pr["proc_label"].dropna().astype(str)))

        # demographics + comorbidities
        demo = {"subject_id": subject_id, "hadm_id": hadm_id}
        if subject_id in self.patients.index:
            p = self.patients.loc[subject_id]
            demo.update(gender=str(p["gender"]), anchor_age=int(p["anchor_age"]))
            if int(p["anchor_age"]) >= 89:                       # proposal: exclude 89+ (MIMIC 91 sentinel)
                raise KeyError(f"{proc_uid}: patient age>=89 excluded")
        dcodes = self.diag[self.diag["hadm_id"] == hadm_id]["icd_code"].astype(str).tolist()
        comorbid = {k: v for k, v in build_comorbidity_vector(dcodes).items() if v}

        return {
            "proc_uid": proc_uid, "hadm_id": hadm_id, "subject_id": subject_id,
            "time_zero": str(start), "time_zero_policy": "procedure_start",
            "procedure": {"itemid": int(row["proc_itemid"]), "label": str(row["proc_label"]),
                          "starttime": str(start)},
            "prior_procedures": prior,
            "demographics": demo,
            "comorbidities": comorbid,
            "pre_labs_summary": pre_summary,
            "microbiology": summarize_micro(micro, start),
            "medications": summarize_meds(meds, start),
            "trajectories": trajs,                 # GROUND TRUTH: {lab: {direction, ...}}
            "n_traj_labs": int(row["n_traj_labs"]),
        }


if __name__ == "__main__":
    import json, sys
    from qgen.config import load_config
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else None)
    store = ContextStore(cfg)
    pid = sys.argv[2] if len(sys.argv) > 2 else store.pool[0]
    ctx = store.build_context(pid)
    prev = dict(ctx); prev["trajectories"] = {k: v["direction"] for k, v in ctx["trajectories"].items()}
    print(json.dumps(prev, indent=2, default=str)[:2500])
