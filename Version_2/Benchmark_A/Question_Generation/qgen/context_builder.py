"""Per-admission clinical context for question generation.

build_context(hadm_id) -> dict with demographics, comorbidities, pre-anchor labs (full timestamped
series + summary), pre-anchor microbiology, and the time-zero anchor. Everything returned is BEFORE
time-zero (no leakage). Reuses the pure extractors in qgen.mimic_features.

Lab/micro rows come from the per-admission parquet slices materialized by qgen.cohort
(outputs/eligible_labs/<hadm>_labs.parquet / _micro.parquet). Small metadata tables
(patients/admissions/diagnoses) are loaded once and cached.
"""
from __future__ import annotations

import pandas as pd

from qgen.config import mimic_root, out_dir
from qgen.mimic_features import (build_comorbidity_vector, pre_labs_full,
                                 summarize_all_labs, summarize_meds, summarize_micro)


class ContextStore:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.root = mimic_root(cfg)
        od = out_dir(cfg)
        self.labs_path = od / "eligible_labs.parquet"
        self.micro_path = od / "eligible_micro.parquet"
        self.meds_path = od / "eligible_meds.parquet"
        self.index = pd.read_parquet(od / "eligible_index.parquet").set_index("hadm_id")
        # admissions with materialized slices (the sampling pool); fall back to full index
        pool_path = od / "pool.parquet"
        if pool_path.exists():
            self.pool = pd.read_parquet(pool_path)["hadm_id"].astype("int64").tolist()
        else:
            self.pool = list(self.index.index)
        self._patients = None
        self._adm = None
        self._diag_by_hadm = None
        self._labs_by = None       # hadm_id -> labs df (loaded once, in-memory)
        self._micro_by = None
        self._meds_by = None

    # ── cached metadata ──────────────────────────────────────────────────────
    def _gz(self, subdir, table):
        p = self.root / subdir / f"{table}.csv.gz"
        return p if p.exists() else self.root / subdir / f"{table}.csv"

    @property
    def patients(self):
        if self._patients is None:
            df = pd.read_csv(self._gz("hosp", "patients"),
                             usecols=["subject_id", "gender", "anchor_age", "anchor_year_group", "dod"])
            self._patients = df.set_index("subject_id")
        return self._patients

    @property
    def adm(self):
        if self._adm is None:
            df = pd.read_csv(self._gz("hosp", "admissions"),
                             usecols=["subject_id", "hadm_id", "admittime", "dischtime", "deathtime",
                                      "admission_type", "admission_location", "race",
                                      "hospital_expire_flag"],
                             parse_dates=["admittime", "dischtime", "deathtime"], low_memory=False)
            self._adm = df.set_index("hadm_id")
        return self._adm

    @property
    def diag_by_hadm(self):
        if self._diag_by_hadm is None:
            df = pd.read_csv(self._gz("hosp", "diagnoses_icd"),
                             usecols=["hadm_id", "icd_code", "icd_version", "seq_num"])
            self._diag_by_hadm = df.sort_values("seq_num")
        return self._diag_by_hadm

    # ── time-zero ────────────────────────────────────────────────────────────
    def _anchor(self, hadm_id: int, adm_micro: pd.DataFrame):
        tz = self.cfg["time_zero"]
        if tz["policy"] == "first_micro" and adm_micro is not None and len(adm_micro):
            return adm_micro["charttime"].min()
        intime = pd.to_datetime(self.index.loc[hadm_id, "icu_intime"])
        return intime + pd.Timedelta(hours=float(tz.get("offset_hours", 24)))

    # ── slices (loaded once into memory, grouped by hadm — fast per-item access) ──
    def _ensure_loaded(self):
        if self._labs_by is None:
            d = pd.read_parquet(self.labs_path) if self.labs_path.exists() else None
            if d is not None and "charttime" in d:
                d["charttime"] = pd.to_datetime(d["charttime"], errors="coerce")
            self._labs_by = {h: g for h, g in d.groupby("hadm_id")} if d is not None else {}
            m = pd.read_parquet(self.micro_path) if self.micro_path.exists() else None
            if m is not None and "charttime" in m:
                m["charttime"] = pd.to_datetime(m["charttime"], errors="coerce")
            self._micro_by = {h: g for h, g in m.groupby("hadm_id")} if m is not None else {}
            md = pd.read_parquet(self.meds_path) if self.meds_path.exists() else None
            if md is not None and "starttime" in md:
                md["starttime"] = pd.to_datetime(md["starttime"], errors="coerce")
            self._meds_by = {h: g for h, g in md.groupby("hadm_id")} if md is not None else {}

    def _load_slice(self, hadm_id: int, kind: str) -> pd.DataFrame | None:
        self._ensure_loaded()
        df = {"labs": self._labs_by, "micro": self._micro_by, "meds": self._meds_by}[kind].get(hadm_id)
        if df is None or len(df) == 0:
            return None
        if "charttime" in df:
            df["charttime"] = pd.to_datetime(df["charttime"], errors="coerce")
        return df

    # ── main ─────────────────────────────────────────────────────────────────
    def build_context(self, hadm_id: int) -> dict:
        hadm_id = int(hadm_id)
        if hadm_id not in self.index.index:
            raise KeyError(f"{hadm_id} not in eligible index")
        row = self.index.loc[hadm_id]
        subject_id = int(row["subject_id"])

        labs = self._load_slice(hadm_id, "labs")
        micro = self._load_slice(hadm_id, "micro")
        meds = self._load_slice(hadm_id, "meds")
        anchor = self._anchor(hadm_id, micro)

        # demographics
        demo = {"subject_id": subject_id, "hadm_id": hadm_id}
        if subject_id in self.patients.index:
            p = self.patients.loc[subject_id]
            demo.update(gender=str(p["gender"]), anchor_age=int(p["anchor_age"]))
            if int(p["anchor_age"]) >= 89:                       # proposal: exclude 89+ (MIMIC 91 sentinel)
                raise KeyError(f"{hadm_id}: patient age>=89 excluded")
        if hadm_id in self.adm.index:
            a = self.adm.loc[hadm_id]
            demo.update(admission_type=str(a["admission_type"]), race=str(a["race"]),
                        hospital_expire_flag=int(a["hospital_expire_flag"]))

        # comorbidities from this admission's diagnoses
        dcodes = self.diag_by_hadm[self.diag_by_hadm["hadm_id"] == hadm_id]["icd_code"].astype(str).tolist()
        comorbid = build_comorbidity_vector(dcodes)

        return {
            "hadm_id": hadm_id,
            "subject_id": subject_id,
            "time_zero": str(anchor),
            "time_zero_policy": f"{self.cfg['time_zero']['policy']}(+{self.cfg['time_zero'].get('offset_hours')}h)",
            "demographics": demo,
            "comorbidities": {k: v for k, v in comorbid.items() if v},
            "labs_full": pre_labs_full(labs, anchor),
            "labs_summary": summarize_all_labs(labs, anchor),
            "microbiology": summarize_micro(micro, anchor),
            "medications": summarize_meds(meds, anchor),
            "cohort_stats": {"n_labs": int(row["n_labs"]), "n_distinct_itemids": int(row["n_distinct_itemids"]),
                             "n_abnormal": int(row["n_abnormal"]), "n_micro": int(row["n_micro"])},
        }


if __name__ == "__main__":
    import json, sys
    from qgen.config import load_config
    cfg = load_config()
    store = ContextStore(cfg)
    hid = int(sys.argv[1]) if len(sys.argv) > 1 else int(store.index.index[0])
    ctx = store.build_context(hid)
    # compact preview
    ctx_preview = dict(ctx)
    ctx_preview["labs_full"] = {k: f"[{len(v)} pts]" for k, v in ctx["labs_full"].items()}
    print(json.dumps(ctx_preview, indent=2, default=str)[:3000])
