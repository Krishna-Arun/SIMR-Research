"""
Context builder — MIMIC-IV (demo) -> Benchmark C intervention-attribution contexts.

Pipeline:
  1. Build "units": one per clinical procedure with enough surrounding lab sampling.
     A unit carries its core labs (>=2 pre & >=2 post-72h, valid ref range) with pre
     and post values, its pre-procedure lab panel, and its prior procedures.
  2. Pair units so the two patients have DIFFERENT procedure types, DIFFERENT subjects,
     >= MIN_SHARED_LABS shared core labs, and a SIMILAR pre-state (small z-distance).
  3. Assemble a record: both patients' pre-states + procedures, one observed post-panel
     (restricted to shared labs) from the ground-truth patient, and the answer.

Self-contained (own MimicDemo). Scales to full MIMIC-IV by swapping the loader.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from prompts import (MAX_PRESTATE_DISTANCE, MIN_SHARED_LABS, POST_WINDOW_HOURS)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIMIC_ROOT = REPO_ROOT / "mimic-iv-clinical-database-demo-2.2"

_EXCLUDE_CATEGORIES = {"Communication"}
# C wants THERAPEUTIC interventions with physiologic effects — drop diagnostic /
# monitoring / documentation events (they have little causal lab signal).
_EXCLUDE_LABEL_SUBSTR = ("updated by", "culture", "x-ray", "echo", "family", "gauge",
                         "ekg", "ct scan", "mri", "ultrasound", "imaging", "monitor",
                         "or received", "or sent", "transport")
MIN_PRE = 2
MIN_POST = 2
MAX_UNITS = 400          # cap the O(n^2) pairing search


def _csv(subdir, table):
    p = MIMIC_ROOT / subdir / f"{table}.csv.gz"
    return p if p.exists() else MIMIC_ROOT / subdir / f"{table}.csv"


def _dt(s):
    return pd.to_datetime(s, errors="coerce")


class MimicDemo:
    def __init__(self, root: Path = MIMIC_ROOT):
        self.root = root
        self._cache: dict = {}
        self._groups: dict = {}

    def t(self, subdir, table, **kw):
        key = f"{subdir}/{table}"
        if key not in self._cache:
            self._cache[key] = pd.read_csv(_csv(subdir, table), low_memory=False, **kw)
        return self._cache[key]

    def group_by(self, subdir, table, col):
        gk = f"{subdir}/{table}#{col}"
        if gk not in self._groups:
            df = self.t(subdir, table)
            self._groups[gk] = ({k: g for k, g in df.groupby(col)} if col in df.columns else {})
        return self._groups[gk]

    def labitem_label(self):
        d = self.t("hosp", "d_labitems")
        return dict(zip(d["itemid"], d["label"]))

    def item_label(self):
        d = self.t("icu", "d_items")
        return dict(zip(d["itemid"], d["label"]))


def _zmid(value, lo, hi):
    """z relative to reference-range center, scaled by half-width -> ~[-1,1] in range."""
    half = (hi - lo) / 2.0
    return (value - (lo + hi) / 2.0) / half if half > 0 else 0.0


class ContextBuilder:
    def __init__(self, demo: MimicDemo | None = None):
        self.db = demo or MimicDemo()
        self._labels = self.db.labitem_label()
        self._ilabels = self.db.item_label()
        self._units: list[dict] | None = None

    def _procedures(self) -> pd.DataFrame:
        pe = self.db.t("icu", "procedureevents").copy()
        pe["starttime"] = _dt(pe["starttime"])
        pe = pe[pe["starttime"].notna()]
        pe["label"] = pe["itemid"].map(self._ilabels).astype(str)
        cat = pe.get("ordercategoryname", pd.Series([""] * len(pe))).astype(str)
        keep = ~cat.isin(_EXCLUDE_CATEGORIES)
        low = pe["label"].str.lower()
        for sub in _EXCLUDE_LABEL_SUBSTR:
            keep &= ~low.str.contains(sub, regex=False)
        return pe[keep]

    def _core_labs(self, hadm_id, t0) -> dict:
        L = self.db.group_by("hosp", "labevents", "hadm_id").get(hadm_id)
        if L is None or not len(L):
            return {}
        L = L.copy(); L["charttime"] = _dt(L["charttime"])
        hi = t0 + pd.Timedelta(hours=POST_WINDOW_HOURS)
        pre_all = L[L["charttime"] < t0]
        post_all = L[(L["charttime"] > t0) & (L["charttime"] <= hi)]
        core = {}
        for itid in set(pre_all["itemid"]).intersection(post_all["itemid"]):
            pre = pre_all[(pre_all["itemid"] == itid) & pre_all["valuenum"].notna()].sort_values("charttime")
            post = post_all[(post_all["itemid"] == itid) & post_all["valuenum"].notna()].sort_values("charttime")
            if len(pre) < MIN_PRE or len(post) < MIN_POST:
                continue
            rl, rh = pre.iloc[-1].get("ref_range_lower"), pre.iloc[-1].get("ref_range_upper")
            try:
                rl, rh = float(rl), float(rh)
            except (TypeError, ValueError):
                continue
            if not (rh - rl > 0):        # skips NaN ranges too (NaN > 0 is False)
                continue
            name = self._labels.get(itid, str(itid))
            pre_v, post_v = float(pre.iloc[-1]["valuenum"]), float(post.iloc[-1]["valuenum"])
            core[name] = {"ref_low": rl, "ref_high": rh, "pre_value": pre_v, "post_value": post_v,
                          "pre_time": str(pre.iloc[-1]["charttime"]),
                          "post_times": [str(x) for x in post["charttime"].tolist()],
                          "unit": pre.iloc[-1].get("valueuom"), "z": _zmid(pre_v, rl, rh)}
        return core

    def _pre_labs(self, hadm_id, t0):
        L = self.db.group_by("hosp", "labevents", "hadm_id").get(hadm_id)
        if L is None or not len(L):
            return []
        L = L.copy(); L["charttime"] = _dt(L["charttime"])
        out = []
        for _, r in L[L["charttime"] < t0].iterrows():
            out.append({"lab": self._labels.get(r["itemid"], str(r["itemid"])),
                        "value": r.get("value"), "valuenum": r.get("valuenum"),
                        "unit": r.get("valueuom"), "flag": r.get("flag"),
                        "charttime": str(r["charttime"])})
        return out

    def _prior_procedures(self, hadm_id, t0):
        pe = self._procedures()
        rows = pe[(pe["hadm_id"] == hadm_id) & (pe["starttime"] < t0)]
        return sorted({str(r["label"]) for _, r in rows.iterrows()})

    def units(self) -> list[dict]:
        if self._units is not None:
            return self._units
        seen = set()
        units = []
        for _, p in self._procedures().iterrows():
            if pd.isna(p["hadm_id"]):
                continue
            hadm_id, subject_id = int(p["hadm_id"]), int(p["subject_id"])
            key = (subject_id, str(p["label"]))       # one unit per (patient, procedure type)
            if key in seen:
                continue
            core = self._core_labs(hadm_id, p["starttime"])
            if len(core) < MIN_SHARED_LABS:
                continue
            seen.add(key)
            units.append({"subject_id": subject_id, "hadm_id": hadm_id,
                          "proc_itemid": int(p["itemid"]), "proc_name": str(p["label"]),
                          "t0": p["starttime"], "core": core})
            if len(units) >= MAX_UNITS:
                break
        self._units = units
        return units

    @staticmethod
    def _distance(uA, uB):
        shared = sorted(set(uA["core"]).intersection(uB["core"]))
        if len(shared) < MIN_SHARED_LABS:
            return None, shared
        d = sum(abs(uA["core"][l]["z"] - uB["core"][l]["z"]) for l in shared) / len(shared)
        return d, shared

    # procedure families with DIVERGENT, lab-visible effects — the only pairs where
    # "which patient does this post-panel belong to?" is decidable from procedure effects.
    _FAMILIES = {"dialysis": ("dialysis", "crrt", "hemodialysis", "renal replacement"),
                 "transfusion": ("transfusion", "packed red", "prbc", "red blood cell"),
                 "ventilation": ("intubation", "invasive ventilation", "mechanical ventilation")}

    def _family(self, name):
        low = str(name).lower()
        for fam, keys in self._FAMILIES.items():
            if any(k in low for k in keys):
                return fam
        return None

    def pair_units(self, require_divergent_families: bool = True):
        """Greedy matching: each unit used once; partners = different subject, similar
        pre-state, and (by default) DIFFERENT lab-effect FAMILIES so the observed panel
        can discriminate them. Yields (uA, uB, shared_labs, distance)."""
        units = self.units()
        used = set()
        for i, uA in enumerate(units):
            if i in used:
                continue
            fa = self._family(uA["proc_name"])
            if require_divergent_families and fa is None:
                continue
            best = None
            for j in range(i + 1, len(units)):
                if j in used:
                    continue
                uB = units[j]
                if uB["subject_id"] == uA["subject_id"] or uB["proc_name"] == uA["proc_name"]:
                    continue
                fb = self._family(uB["proc_name"])
                if require_divergent_families and (fb is None or fb == fa):
                    continue
                d, shared = self._distance(uA, uB)
                if d is None or d > MAX_PRESTATE_DISTANCE:
                    continue
                if best is None or d < best[0]:
                    best = (d, j, uB, shared)
            if best is not None:
                d, j, uB, shared = best
                used.add(i); used.add(j)
                yield uA, uB, shared, d

    def build_context(self, uA, uB, shared, distance, answer: str) -> dict:
        """answer in {'A','B'} selects whose post-panel is observed."""
        winner = uA if answer == "A" else uB

        def patient(u):
            return {"subject_id": str(u["subject_id"]), "hadm_id": str(u["hadm_id"]),
                    "procedure": {"name": u["proc_name"], "time": str(u["t0"])},
                    "prior_procedures": self._prior_procedures(u["hadm_id"], u["t0"]),
                    "pre_labs": self._pre_labs(u["hadm_id"], u["t0"])}

        observed = [{"lab": l, "value": winner["core"][l]["post_value"],
                     "unit": winner["core"][l]["unit"],
                     "charttime": (winner["core"][l]["post_times"] or ["+<=72h"])[-1]}
                    for l in shared]
        return {"question_type": "intervention_attribution",
                "patient_A": patient(uA), "patient_B": patient(uB),
                "shared_labs": shared,
                "observed_post": {"labs": observed},
                "answer": answer,
                "pre_state_distance": round(float(distance), 4),
                # convenience for the generator (not part of the answering view):
                "_winner_effects": {l: {"pre": winner["core"][l]["pre_value"],
                                        "post": winner["core"][l]["post_value"]} for l in shared}}


if __name__ == "__main__":
    cb = ContextBuilder()
    print(f"units: {len(cb.units())}")
    pairs = list(cb.pair_units())
    print(f"pairs found: {len(pairs)}")
    for k, (uA, uB, shared, d) in enumerate(pairs[:3]):
        print(f"  pair {k}: A={uA['proc_name']}({uA['subject_id']}) vs "
              f"B={uB['proc_name']}({uB['subject_id']}) | shared={len(shared)} | dist={d:.3f}")
    if pairs:
        uA, uB, shared, d = pairs[0]
        ctx = cb.build_context(uA, uB, shared, d, "A")
        print("\nexample shared labs:", ctx["shared_labs"][:8])
        print("observed post (first 3):", ctx["observed_post"]["labs"][:3])
