"""
Context builder — MIMIC-IV (demo) -> per-(patient, admission, question_type) context.

Turns a real admission into the object the generation agents see and, later, the
values the supplemental MCP server hands out. Enforces anti-leakage IN DATA:
everything in `pre_t0` is strictly before time-zero; the post-t0 rows are used
only to derive the ground-truth `outcome` (which the answering agent never sees).

Self-contained: reads the demo CSVs directly with pandas (the demo is small —
~108K labs). To scale to full MIMIC-IV, swap MimicDemo for a cohort/parquet
loader; the context contract stays identical.

Question types & time-zero (see prompts.TARGET_DEFS):
  next_procedure   -> ICU intime (fallback admit)
  deterioration    -> admit + 24h
  readmission_30d  -> dischtime
  mortality_1y     -> dischtime
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# repo_root/mimic-iv-clinical-database-demo-2.2
REPO_ROOT = Path(__file__).resolve().parents[3]
MIMIC_ROOT = REPO_ROOT / "mimic-iv-clinical-database-demo-2.2"

QUESTION_TYPES = ("next_procedure", "deterioration", "readmission_30d", "mortality_1y")

# ICU d_items labels we treat as "vitals" (substring match, case-insensitive).
_VITAL_KEYWORDS = ("heart rate", "arterial blood pressure", "non invasive blood pressure",
                   "respiratory rate", "o2 saturation", "spo2", "temperature")


def _csv(subdir: str, table: str) -> Path:
    p = MIMIC_ROOT / subdir / f"{table}.csv.gz"
    return p if p.exists() else MIMIC_ROOT / subdir / f"{table}.csv"


class MimicDemo:
    """Lazily loads + caches the demo tables needed for context building."""

    def __init__(self, root: Path = MIMIC_ROOT):
        self.root = root
        self._cache: dict[str, pd.DataFrame] = {}
        self._groups: dict[str, dict] = {}

    def t(self, subdir: str, table: str, **read_kwargs) -> pd.DataFrame:
        key = f"{subdir}/{table}"
        if key not in self._cache:
            self._cache[key] = pd.read_csv(_csv(subdir, table), low_memory=False, **read_kwargs)
        return self._cache[key]

    def group_by(self, subdir: str, table: str, col: str) -> dict:
        """Return {key_value: sub-DataFrame} grouped once and cached.

        Turns the per-admission scans (previously O(table) each call) into a dict
        lookup — essential for iter_eligible, which builds ~1000 contexts.
        """
        gkey = f"{subdir}/{table}#{col}"
        if gkey not in self._groups:
            df = self.t(subdir, table)
            self._groups[gkey] = ({k: g for k, g in df.groupby(col)} if col in df.columns else {})
        return self._groups[gkey]

    # ---- dictionaries -----------------------------------------------------
    def labitem_label(self) -> dict:
        d = self.t("hosp", "d_labitems")
        return dict(zip(d["itemid"], d["label"]))

    def item_label(self) -> dict:
        d = self.t("icu", "d_items")
        return dict(zip(d["itemid"], d["label"]))

    def icd_dx_title(self) -> dict:
        d = self.t("hosp", "d_icd_diagnoses")
        return dict(zip(zip(d["icd_code"], d["icd_version"]), d["long_title"]))

    def icd_proc_title(self) -> dict:
        d = self.t("hosp", "d_icd_procedures")
        return dict(zip(zip(d["icd_code"], d["icd_version"]), d["long_title"]))


def _dt(s):
    return pd.to_datetime(s, errors="coerce")


class ContextBuilder:
    def __init__(self, demo: MimicDemo | None = None):
        self.db = demo or MimicDemo()

    # ── time-zero ──────────────────────────────────────────────────────────
    def _time_zero(self, hadm_id: int, admit, disch, qtype: str):
        if qtype == "next_procedure":
            rows = self.db.group_by("icu", "icustays", "hadm_id").get(hadm_id)
            if rows is not None and len(rows):
                return _dt(rows["intime"]).min(), "ICU intime"
            return admit, "hospital admit (no ICU stay)"
        if qtype == "deterioration":
            return admit + pd.Timedelta(hours=24), "admit + 24h"
        if qtype in ("readmission_30d", "mortality_1y"):
            return disch, "dischtime"
        raise ValueError(qtype)

    # ── supplemental pools (all strictly BEFORE time-zero) ──────────────────
    def _labs(self, hadm_id, subject_id, t0):
        df = self.db.group_by("hosp", "labevents", "hadm_id").get(hadm_id)
        if df is None or not len(df):
            return []
        df = df.copy()
        df["charttime"] = _dt(df["charttime"])
        df = df[df["charttime"] < t0]
        labels = self.db.labitem_label()
        out = []
        for _, r in df.iterrows():
            out.append({
                "item_name": labels.get(r["itemid"], str(r["itemid"])),
                "value": r.get("value"), "valuenum": r.get("valuenum"),
                "unit": r.get("valueuom"),
                "ref_low": r.get("ref_range_lower"), "ref_high": r.get("ref_range_upper"),
                "flag": r.get("flag"), "charttime": str(r["charttime"]),
            })
        return out

    def _microbiology(self, hadm_id, t0):
        df = self.db.group_by("hosp", "microbiologyevents", "hadm_id").get(hadm_id)
        if df is None or not len(df):
            return []
        df = df.copy()
        df["charttime"] = _dt(df["charttime"].fillna(df["chartdate"]))
        df = df[df["charttime"] < t0]
        return [{
            "spec_type": r.get("spec_type_desc"), "test_name": r.get("test_name"),
            "organism": r.get("org_name"), "antibiotic": r.get("ab_name"),
            "interpretation": r.get("interpretation"), "charttime": str(r["charttime"]),
        } for _, r in df.iterrows()]

    def _medications(self, hadm_id, t0):
        df = self.db.group_by("hosp", "prescriptions", "hadm_id").get(hadm_id)
        if df is None or not len(df):
            return []
        df = df.copy()
        df["starttime"] = _dt(df["starttime"])
        df = df[df["starttime"] < t0]
        return [{
            "drug": r.get("drug"), "dose": r.get("dose_val_rx"),
            "unit": r.get("dose_unit_rx"), "route": r.get("route"),
            "starttime": str(r["starttime"]),
        } for _, r in df.iterrows()]

    def _vitals_exam(self, hadm_id, subject_id, t0):
        out = []
        # outpatient OMR (by subject + chartdate)
        omr = self.db.group_by("hosp", "omr", "subject_id").get(subject_id)
        if omr is not None and len(omr):
            omr = omr.copy()
            omr["chartdate"] = _dt(omr["chartdate"])
            omr = omr[omr["chartdate"] < t0]
            for _, r in omr.iterrows():
                out.append({"source": "omr", "item_name": r.get("result_name"),
                            "value": r.get("result_value"), "charttime": str(r["chartdate"])})
        # ICU chartevents vitals (by hadm), filtered to vital itemids
        ce = self.db.group_by("icu", "chartevents", "hadm_id").get(hadm_id)
        if ce is not None and len(ce):
            ce = ce.copy()
            ce["charttime"] = _dt(ce["charttime"])
            ce = ce[ce["charttime"] < t0]
            labels = self.db.item_label()
            for _, r in ce.iterrows():
                lab = labels.get(r["itemid"], "")
                if any(k in str(lab).lower() for k in _VITAL_KEYWORDS):
                    out.append({"source": "chartevents", "item_name": lab,
                                "value": r.get("value"), "unit": r.get("valueuom"),
                                "charttime": str(r["charttime"])})
        return out

    def _dx_history(self, subject_id, t0):
        """Comorbidities from PRIOR admissions discharged before time-zero (leak-safe)."""
        adm = self._admission_rows()
        adm = adm[adm["subject_id"] == subject_id]
        prior = adm[adm["dischtime"] < t0]["hadm_id"].tolist()
        if not prior:
            return []
        dxg = self.db.group_by("hosp", "diagnoses_icd", "hadm_id")
        titles = self.db.icd_dx_title()
        dx = pd.concat([dxg[h] for h in prior if h in dxg], ignore_index=True) \
            if any(h in dxg for h in prior) else pd.DataFrame(columns=["icd_code", "icd_version"])
        return [{"icd_code": r["icd_code"],
                 "title": titles.get((r["icd_code"], r["icd_version"]), "")}
                for _, r in dx.iterrows()]

    def _prior_procedures(self, subject_id, t0):
        pr = self.db.group_by("hosp", "procedures_icd", "subject_id").get(subject_id)
        if pr is None or not len(pr):
            return []
        pr = pr.copy()
        pr["chartdate"] = _dt(pr["chartdate"])
        pr = pr[pr["chartdate"] < t0]
        titles = self.db.icd_proc_title()
        return [{"icd_code": r["icd_code"], "chartdate": str(r["chartdate"]),
                 "title": titles.get((r["icd_code"], r["icd_version"]), "")}
                for _, r in pr.iterrows()]

    def _fluids_output(self, hadm_id, t0):
        out = []
        inp = self.db.group_by("icu", "inputevents", "hadm_id").get(hadm_id)
        if inp is not None and len(inp):
            inp = inp.copy()
            inp["starttime"] = _dt(inp["starttime"])
            inp = inp[inp["starttime"] < t0]
            for _, r in inp.iterrows():
                out.append({"direction": "input", "amount": r.get("amount"),
                            "unit": r.get("amountuom"), "charttime": str(r["starttime"])})
        op = self.db.group_by("icu", "outputevents", "hadm_id").get(hadm_id)
        if op is not None and len(op):
            op = op.copy()
            op["charttime"] = _dt(op["charttime"])
            op = op[op["charttime"] < t0]
            for _, r in op.iterrows():
                out.append({"direction": "output", "amount": r.get("value"),
                            "unit": r.get("valueuom"), "charttime": str(r["charttime"])})
        return out

    # ── outcome / label derivation (post-t0; answer key only) ───────────────
    def _outcome(self, subject_id, hadm_id, admit, disch, death, expire_flag, t0, qtype):
        if qtype == "next_procedure":
            items = []
            proc = self.db.group_by("hosp", "procedures_icd", "hadm_id").get(hadm_id)
            if proc is not None and len(proc):
                proc = proc.copy()
                proc["chartdate"] = _dt(proc["chartdate"])
                after = proc[proc["chartdate"] >= t0]
                titles = self.db.icd_proc_title()
                items += [titles.get((r["icd_code"], r["icd_version"]), str(r["icd_code"]))
                          for _, r in after.iterrows()]
            # ICU procedureevents (timed) too
            pe = self.db.group_by("icu", "procedureevents", "hadm_id").get(hadm_id)
            if pe is not None and len(pe):
                pe = pe.copy()
                pe["starttime"] = _dt(pe["starttime"])
                pe = pe[pe["starttime"] >= t0]
                ilab = self.db.item_label()
                items += [ilab.get(r["itemid"], str(r["itemid"])) for _, r in pe.iterrows()]
            return {"label": sorted(set(items)), "positive": bool(items)}

        if qtype == "readmission_30d":
            adm = self._admission_rows()
            adm = adm[adm["subject_id"] == subject_id]
            future = adm[adm["admittime"] > disch]
            if not len(future):
                return {"label": False, "positive": False, "gap_days": None}
            gap = (future["admittime"].min() - disch).days
            return {"label": bool(gap <= 30), "positive": bool(gap <= 30), "gap_days": int(gap)}

        if qtype == "mortality_1y":
            dod = _dt(pd.Series([death]))[0]
            # patients.dod is date-level; prefer it, else admission deathtime
            pat = self.db.t("hosp", "patients")
            prow = pat[pat["subject_id"] == subject_id]
            if len(prow) and pd.notna(prow.iloc[0].get("dod")):
                dod = _dt(pd.Series([prow.iloc[0]["dod"]]))[0]
            if pd.isna(dod):
                return {"label": False, "positive": False, "days_to_death": None}
            days = (dod - disch).days
            return {"label": bool(0 <= days <= 365), "positive": bool(0 <= days <= 365),
                    "days_to_death": int(days)}

        if qtype == "deterioration":
            rows = self.db.group_by("icu", "icustays", "hadm_id").get(hadm_id)
            positive = False
            if rows is not None and len(rows):
                positive = bool((_dt(rows["intime"]) >= t0).any())
            # in-hospital death after t0 also counts as deterioration
            dt_death = _dt(pd.Series([death]))[0]
            if pd.notna(dt_death) and dt_death >= t0:
                positive = True
            return {"label": positive, "positive": positive}

        raise ValueError(qtype)

    # ── eligibility + main ──────────────────────────────────────────────────
    def _admission_rows(self):
        if getattr(self, "_adm_cache", None) is None:
            adm = self.db.t("hosp", "admissions").copy()
            for c in ("admittime", "dischtime", "deathtime"):
                adm[c] = _dt(adm[c])
            self._adm_cache = adm
        return self._adm_cache

    def is_eligible(self, hadm_id: int, qtype: str) -> bool:
        try:
            ctx = self.build_context(int(hadm_id), qtype)
        except Exception:
            return False
        # need some pre-t0 signal AND a computable, non-degenerate label
        has_signal = any(len(ctx["pre_t0"][k]) for k in ctx["pre_t0"])
        if not has_signal:
            return False
        if qtype == "next_procedure":
            return ctx["outcome"]["positive"]         # something must happen next
        return ctx["outcome"]["label"] is not None

    def iter_eligible(self, qtypes=QUESTION_TYPES):
        adm = self._admission_rows()
        for _, a in adm.iterrows():
            for qt in qtypes:
                # readmission/mortality need a discharge; skip in-hospital deaths for readmission
                if qt == "readmission_30d" and a["hospital_expire_flag"] == 1:
                    continue
                if pd.isna(a["dischtime"]) and qt in ("readmission_30d", "mortality_1y"):
                    continue
                if self.is_eligible(int(a["hadm_id"]), qt):
                    yield {"subject_id": int(a["subject_id"]),
                           "hadm_id": int(a["hadm_id"]), "question_type": qt}

    def build_context(self, hadm_id: int, qtype: str) -> dict:
        if qtype not in QUESTION_TYPES:
            raise ValueError(f"unknown question_type {qtype}")
        adm = self._admission_rows()
        row = adm[adm["hadm_id"] == hadm_id]
        if not len(row):
            raise KeyError(f"hadm_id {hadm_id} not found")
        a = row.iloc[0]
        subject_id = int(a["subject_id"])
        admit, disch, death = a["admittime"], a["dischtime"], a["deathtime"]

        t0, policy = self._time_zero(hadm_id, admit, disch, qtype)

        pat = self.db.t("hosp", "patients")
        prow = pat[pat["subject_id"] == subject_id]
        demo = {"subject_id": subject_id, "hadm_id": int(hadm_id),
                "gender": str(prow.iloc[0]["gender"]) if len(prow) else None,
                "anchor_age": int(prow.iloc[0]["anchor_age"]) if len(prow) else None,
                "admission_type": str(a["admission_type"]), "race": str(a["race"])}

        pre_t0 = {
            "labs": self._labs(hadm_id, subject_id, t0),
            "microbiology": self._microbiology(hadm_id, t0),
            "medications": self._medications(hadm_id, t0),
            "vitals_exam": self._vitals_exam(hadm_id, subject_id, t0),
            "dx_history": self._dx_history(subject_id, t0),
            "prior_procedures": self._prior_procedures(subject_id, t0),
            "fluids_output": self._fluids_output(hadm_id, t0),
        }
        outcome = self._outcome(subject_id, hadm_id, admit, disch, death,
                                a["hospital_expire_flag"], t0, qtype)
        return {
            "patient": demo,
            "question_type": qtype,
            "time_zero": str(t0),
            "time_zero_policy": policy,
            "pre_t0": pre_t0,
            "outcome": outcome,       # answer key only — NEVER shown to the answering agent
        }


def to_supplemental_bundle(context: dict, question_id: str) -> dict:
    """Answering-agent-facing view of a context: pre_t0 pools only, NO outcome.

    This is exactly what the supplementals MCP server serves. Each item keeps its
    name/date (listable without values) plus its value payload (revealed only on
    Request_a_supplemental).
    """
    return {
        "question_id": question_id,
        "subject_id": context["patient"]["subject_id"],
        "hadm_id": context["patient"]["hadm_id"],
        "question_type": context["question_type"],
        "time_zero": context["time_zero"],
        "supplementals": context["pre_t0"],       # outcome intentionally omitted
    }


if __name__ == "__main__":
    cb = ContextBuilder()
    elig = list(cb.iter_eligible())
    print(f"eligible (patient, admission, type) tuples: {len(elig)}")
    from collections import Counter
    print("by type:", dict(Counter(e["question_type"] for e in elig)))
    if elig:
        ex = elig[0]
        ctx = cb.build_context(ex["hadm_id"], ex["question_type"])
        print(f"\nexample: hadm={ex['hadm_id']} type={ex['question_type']} t0={ctx['time_zero']} ({ctx['time_zero_policy']})")
        print("pre_t0 counts:", {k: len(v) for k, v in ctx["pre_t0"].items()})
        print("outcome:", ctx["outcome"])
