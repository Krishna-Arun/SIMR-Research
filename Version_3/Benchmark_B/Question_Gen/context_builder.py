"""
Context builder — MIMIC-IV (demo) -> Benchmark B lab-trajectory contexts.

For each clinically meaningful procedure with enough surrounding lab sampling,
builds: the pre-procedure observable state (labs+micro with values), the target
core labs (>=2 pre & >=2 post-72h measurements, valid reference range), and the
ground-truth post-procedure DIRECTION per core lab (reference-range-relative rule
in prompts.DIRECTION_RULE). Post-procedure VALUES live only in ground_truth
(answer key) — never in `targets`/`inputs`.

Self-contained (own MimicDemo). To scale to full MIMIC-IV, swap the loader; the
context contract is unchanged.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from prompts import POST_WINDOW_HOURS, STABLE_BAND_FRAC

REPO_ROOT = Path(__file__).resolve().parents[3]
MIMIC_ROOT = REPO_ROOT / "mimic-iv-clinical-database-demo-2.2"

# procedureevents categories/labels that are NOT clinical interventions.
_EXCLUDE_CATEGORIES = {"Communication"}
_EXCLUDE_LABEL_SUBSTR = ("updated by", "cultured", "x-ray", "echo", "family", "gauge")
MIN_CORE_LABS = 3
MIN_PRE = 2
MIN_POST = 2


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


class ContextBuilder:
    def __init__(self, demo: MimicDemo | None = None):
        self.db = demo or MimicDemo()
        self._labels = self.db.labitem_label()
        self._ilabels = self.db.item_label()

    def _procedures(self) -> pd.DataFrame:
        """Clinically meaningful, timestamped ICU procedure events."""
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

    def _core_labs(self, hadm_id, t0):
        """Return list of core-lab dicts with pre/post series and direction."""
        L = self.db.group_by("hosp", "labevents", "hadm_id").get(hadm_id)
        if L is None or not len(L):
            return []
        L = L.copy()
        L["charttime"] = _dt(L["charttime"])
        win_hi = t0 + pd.Timedelta(hours=POST_WINDOW_HOURS)
        pre_all = L[L["charttime"] < t0]
        post_all = L[(L["charttime"] > t0) & (L["charttime"] <= win_hi)]
        out = []
        for itid in set(pre_all["itemid"]).intersection(post_all["itemid"]):
            pre = pre_all[pre_all["itemid"] == itid].sort_values("charttime")
            post = post_all[post_all["itemid"] == itid].sort_values("charttime")
            pre = pre[pre["valuenum"].notna()]
            post = post[post["valuenum"].notna()]
            if len(pre) < MIN_PRE or len(post) < MIN_POST:
                continue
            rl, rh = pre.iloc[-1].get("ref_range_lower"), pre.iloc[-1].get("ref_range_upper")
            try:
                rl, rh = float(rl), float(rh)
            except (TypeError, ValueError):
                continue
            width = rh - rl
            if not (width > 0):          # skips NaN ranges too (NaN > 0 is False)
                continue
            pre_v, post_v = float(pre.iloc[-1]["valuenum"]), float(post.iloc[-1]["valuenum"])
            delta = post_v - pre_v
            band = STABLE_BAND_FRAC * width
            direction = "Stable" if abs(delta) <= band else ("Rising" if delta > 0 else "Falling")
            out.append({
                "lab": self._labels.get(itid, str(itid)),
                "ref_low": rl, "ref_high": rh, "ref_width": width,
                "pre_value": pre_v, "pre_time": str(pre.iloc[-1]["charttime"]),
                "post_times": [str(x) for x in post["charttime"].tolist()],
                "post_value": post_v, "delta": delta, "direction": direction,
            })
        return out

    def _pre_inputs(self, hadm_id, subject_id, t0):
        labs = []
        L = self.db.group_by("hosp", "labevents", "hadm_id").get(hadm_id)
        if L is not None and len(L):
            L = L.copy(); L["charttime"] = _dt(L["charttime"])
            for _, r in L[L["charttime"] < t0].iterrows():
                labs.append({"lab": self._labels.get(r["itemid"], str(r["itemid"])),
                             "value": r.get("value"), "valuenum": r.get("valuenum"),
                             "unit": r.get("valueuom"), "flag": r.get("flag"),
                             "charttime": str(r["charttime"])})
        micro = []
        M = self.db.group_by("hosp", "microbiologyevents", "hadm_id").get(hadm_id)
        if M is not None and len(M):
            M = M.copy(); M["charttime"] = _dt(M["charttime"].fillna(M["chartdate"]))
            for _, r in M[M["charttime"] < t0].iterrows():
                micro.append({"spec_type": r.get("spec_type_desc"), "test_name": r.get("test_name"),
                              "organism": r.get("org_name"), "antibiotic": r.get("ab_name"),
                              "interpretation": r.get("interpretation"), "charttime": str(r["charttime"])})
        return {"pre_labs": labs, "microbiology": micro}

    def iter_eligible(self):
        """Yield {hadm_id, subject_id, proc_itemid, proc_time, proc_name} for viable questions."""
        for _, p in self._procedures().iterrows():
            hadm_id = int(p["hadm_id"]) if pd.notna(p["hadm_id"]) else None
            if hadm_id is None:
                continue
            core = self._core_labs(hadm_id, p["starttime"])
            if len([c for c in core if c["direction"] != "Stable"]) >= 1 and len(core) >= MIN_CORE_LABS:
                yield {"hadm_id": hadm_id, "subject_id": int(p["subject_id"]),
                       "proc_itemid": int(p["itemid"]), "proc_time": p["starttime"],
                       "proc_name": p["label"]}

    def build_context(self, hadm_id, proc_itemid, proc_time, proc_name) -> dict:
        t0 = pd.to_datetime(proc_time)
        core = self._core_labs(int(hadm_id), t0)
        if len(core) < MIN_CORE_LABS:
            raise ValueError(f"only {len(core)} core labs for hadm {hadm_id} at {t0}")
        adm = self.db.group_by("hosp", "admissions", "hadm_id").get(int(hadm_id))
        subject_id = int(adm.iloc[0]["subject_id"]) if adm is not None and len(adm) else None
        inputs = self._pre_inputs(int(hadm_id), subject_id, t0)

        targets = [{"lab": c["lab"], "ref_low": c["ref_low"], "ref_high": c["ref_high"],
                    "pre_value": c["pre_value"], "pre_time": c["pre_time"],
                    "post_times": c["post_times"]} for c in core]
        ground_truth = [{"lab": c["lab"], "direction": c["direction"], "pre_value": c["pre_value"],
                         "post_value": c["post_value"], "delta": c["delta"],
                         "ref_width": c["ref_width"]} for c in core]
        return {
            "subject_id": subject_id, "hadm_id": int(hadm_id),
            "time_zero": str(t0), "post_window_hours": POST_WINDOW_HOURS,
            "procedures": [{"name": proc_name, "time": str(t0)}],
            "inputs": inputs,
            "targets": targets,
            "ground_truth": ground_truth,   # answer key — never shown to the answering agent
        }


if __name__ == "__main__":
    cb = ContextBuilder()
    elig = list(cb.iter_eligible())
    print(f"eligible procedure-questions: {len(elig)}")
    from collections import Counter
    print("top procedures:", Counter(e["proc_name"] for e in elig).most_common(8))
    if elig:
        e = elig[0]
        ctx = cb.build_context(e["hadm_id"], e["proc_itemid"], e["proc_time"], e["proc_name"])
        print(f"\nexample hadm={e['hadm_id']} proc='{e['proc_name']}' t0={ctx['time_zero']}")
        print("targets:", [(t["lab"]) for t in ctx["targets"]][:8])
        from collections import Counter as C
        print("direction dist:", dict(C(g["direction"] for g in ctx["ground_truth"])))
