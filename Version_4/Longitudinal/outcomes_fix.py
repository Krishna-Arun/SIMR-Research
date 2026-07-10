#!/usr/bin/env python3
"""
V4 outcome fix + balanced-case selection.

Two jobs the V3 pipeline got wrong for the outcome benchmark (d):
  1. `readmission_30d` was 100% negative because cohort_data/admissions.parquet was sliced by
     INDEX hadm_id, so a subject's *later* admissions were dropped. Here we re-derive a TRUE
     30-day readmission from the FULL MIMIC-IV admissions table (all admissions per subject).
     d stays on 1-year mortality, but we report the real readmission rate for the paper.
  2. Mortality is 80%-imbalanced. We select a **balanced** subset of chained cases (~50/50
     mortality) so "always-No" is not an 0.80 free baseline.

Reads:  longitudinal_contexts.json (494 contexts, each with subject_id/hadm_id/A2_outcome)
        ../../2physionet.org/files/mimiciv/3.1/hosp/admissions.csv.gz  (full, local-only)
Writes: longitudinal_contexts.json  (A2_outcome.readmission_30d repaired, in place)
        cohort_data/balanced_cases.json  (subject_ids for a mortality-balanced chained set)

Local PHI only — never committed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]                     # .../SIMR-Research
ADM = REPO / "2physionet.org" / "files" / "mimiciv" / "3.1" / "hosp" / "admissions.csv.gz"
CTX = HERE / "longitudinal_contexts.json"


def _dt(s):
    return pd.to_datetime(s, errors="coerce")


def main(target_n: int = 100):
    data = json.load(open(CTX))
    contexts = data["contexts"]
    subs = {int(c["subject_id"]) for c in contexts}
    print(f"[outcomes_fix] {len(contexts)} contexts, {len(subs)} subjects")

    print(f"[outcomes_fix] loading full admissions ({ADM.name}) …")
    adm = pd.read_csv(ADM, usecols=["subject_id", "hadm_id", "admittime", "dischtime"],
                      low_memory=False)
    adm = adm[adm.subject_id.isin(subs)].copy()
    adm["admittime"] = _dt(adm["admittime"]); adm["dischtime"] = _dt(adm["dischtime"])
    by_sub = {sid: g.sort_values("admittime") for sid, g in adm.groupby("subject_id")}
    print(f"[outcomes_fix] full admissions for cohort: {len(adm)} rows "
          f"(mean {len(adm)/max(len(by_sub),1):.1f} admissions/subject)")

    readm_pos = mort_pos = 0
    for c in contexts:
        sid = int(c["subject_id"]); hadm = int(c["hadm_id"])
        g = by_sub.get(sid)
        readm = False
        if g is not None:
            this = g[g.hadm_id == hadm]
            if len(this):
                disch = this.iloc[0]["dischtime"]
                future = g[g.admittime > disch]
                if len(future) and pd.notna(disch):
                    readm = bool((future.admittime.min() - disch).days <= 30)
        c.setdefault("A2_outcome", {})["readmission_30d"] = readm
        readm_pos += int(readm)
        mort_pos += int(bool((c.get("A2_outcome") or {}).get("mortality_1y")))

    n = len(contexts)
    print(f"\n[outcomes_fix] REPAIRED readmission_30d: {readm_pos}/{n} ({100*readm_pos/n:.1f}%) positive")
    print(f"[outcomes_fix] mortality_1y: {mort_pos}/{n} ({100*mort_pos/n:.1f}%) positive")

    # balanced mortality selection for the chained set, round-robin across arms for diversity
    fam = lambda c: c["anchor"]["family"]

    def round_robin(pool):
        by_fam = {}
        for c in pool:
            by_fam.setdefault(fam(c), []).append(c)
        out, arms = [], list(by_fam)
        i = 0
        while any(by_fam.values()):
            a = arms[i % len(arms)]
            if by_fam[a]:
                out.append(by_fam[a].pop(0))
            i += 1
        return out

    pos = round_robin([c for c in contexts if (c.get("A2_outcome") or {}).get("mortality_1y")])
    neg = round_robin([c for c in contexts if not (c.get("A2_outcome") or {}).get("mortality_1y")])
    half = target_n // 2
    pos, neg = pos[:half], neg[:target_n - half]
    picked = [c for pair in zip(pos, neg) for c in pair]     # INTERLEAVE so any prefix is ~50/50
    picked += pos[len(neg):] + neg[len(pos):]                # tail if uneven
    picked_ids = [c["subject_id"] for c in picked]
    from collections import Counter
    print(f"\n[outcomes_fix] balanced chained set: {len(picked)} cases "
          f"({sum(1 for c in picked if (c.get('A2_outcome') or {}).get('mortality_1y'))} died / "
          f"{len(picked)} total) | arms {dict(Counter(fam(c) for c in picked))}")

    json.dump(data, open(CTX, "w"), default=str)
    (HERE / "cohort_data" / "balanced_cases.json").write_text(
        json.dumps({"target_n": target_n, "subject_ids": picked_ids,
                    "mortality_balance": {"pos": sum(1 for c in picked
                                                     if (c.get('A2_outcome') or {}).get('mortality_1y')),
                                          "n": len(picked)}}, default=str))
    print(f"[outcomes_fix] wrote repaired contexts + cohort_data/balanced_cases.json")


if __name__ == "__main__":
    main()
