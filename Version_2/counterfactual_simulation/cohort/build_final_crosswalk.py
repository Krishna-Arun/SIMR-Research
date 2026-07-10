"""
build_final_crosswalk.py — resolve ALL 529 cohort lab itemids to a decision (100% resolution).

Every itemid ends with exactly one status:
  curated         — hand-verified LOINC (from curated_lab_loinc.json), the 85%-of-volume core
  auto            — matched to LOINC by a PRECISION-CONSTRAINED matcher (every meaningful word of
                    the MIMIC label must appear in the LOINC name), then ranked by Jaccard + specimen
  non_lab         — intentionally NOT a lab analyte (device/vent settings, specimen type, sample-
                    quality indices H/I/L, urine gross appearance) — mapping these would feed CLMBR junk
  unmapped        — a real lab with no confident LOINC candidate (kept honest, not force-mapped)

Reads the full Athena LOINC set with quoting=QUOTE_NONE (the default parser silently drops ~half the
rows on stray ' / " in chemical names — that bug corrupted the earlier fuzzy pass).
"""
from __future__ import annotations

import csv
import re
import json
from pathlib import Path
import pandas as pd

MIMIC = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
D_LABITEMS = MIMIC / "hosp/d_labitems.csv.gz"
ATHENA_CONCEPT = Path("/scratch/users/karun09/Version_2/vocabulary_download_v5_"
                      "{e770b936-2d4a-4239-ad97-64ef3269a20d}_1782458474101/CONCEPT.csv")
OUT_DIR = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/cohort")

# specimen synonyms: MIMIC fluid -> words that should appear in the LOINC name's system part
FLUID_HINTS = {
    "blood": ["serum", "plasma", "blood"], "urine": ["urine"],
    "cerebrospinal fluid": ["cerebral spinal fluid", "spinal fluid", "csf"],
    "other body fluid": ["body fluid"], "ascites": ["peritoneal fluid", "ascites"],
    "pleural": ["pleural fluid"], "joint fluid": ["synovial fluid"], "stool": ["stool", "feces"],
}
STOPWORDS = {"in", "of", "the", "a", "on", "by", "and", "total", "count", "calculated",
             "functional", "whole", "absolute", "automated"}
# analyte-name synonyms so a MIMIC label word matches LOINC's preferred wording
SYNONYM = {"wbc": "leukocyte", "rbc": "erythrocyte", "white": "leukocyte", "red": "erythrocyte"}
# LOINC property markers: quantitative forms are what we want for a numeric state variable; the
# qualitative/ratio forms below are usually the WRONG pick for a serum analyte (e.g. Vancomycin
# [Susceptibility] instead of the drug level, Albumin ratio instead of concentration).
QUANT_MARK = ("mass/volume", "moles/volume", "enzymatic activity", "volume fraction",
              "#/volume", "entitic", "units/volume", "distwidth", "mean volume")
NONQUANT_MARK = ("interpretation", "presence", "susceptibility", "identified")

# itemids that are NOT lab analytes — device/vent settings, specimen meta, sample-quality indices,
# gross-appearance fields. Matched by EXACT lowercased label unless noted.
NON_LAB_EXACT = {
    "specimen type", "intubated", "ventilator", "ventilation rate", "tidal volume", "peep",
    "temperature", "oxygen", "length of urine collection", "urine appearance", "urine color",
    "urine mucous", "i", "h", "l", "comments",
}


def _deplural(t: str) -> str:
    return t[:-1] if (len(t) > 3 and t.endswith("s")) else t


def tokenize(s) -> set:
    if not isinstance(s, str):
        return set()
    toks = {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOPWORDS and len(t) > 1}
    # depluralize + synonym-normalize so "Eosinophil" matches LOINC "Eosinophils", WBC->leukocyte, etc.
    return {SYNONYM.get(_deplural(t), _deplural(t)) for t in toks}


def load_loinc():
    print("loading full LOINC set (QUOTE_NONE) ...")
    rows = []
    for chunk in pd.read_csv(ATHENA_CONCEPT, sep="\t", quoting=csv.QUOTE_NONE, usecols=[
            "concept_name", "domain_id", "vocabulary_id", "concept_class_id",
            "standard_concept", "concept_code"], dtype=str, chunksize=500_000):
        c = chunk[(chunk["vocabulary_id"] == "LOINC") & (chunk["standard_concept"] == "S") &
                  (chunk["domain_id"] == "Measurement") &
                  (chunk["concept_class_id"].isin(["Lab Test", "Clinical Observation"]))]
        rows.append(c[["concept_name", "concept_code"]])
    lo = pd.concat(rows, ignore_index=True).dropna(subset=["concept_name"]).reset_index(drop=True)
    names = lo["concept_name"].tolist()
    codes = lo["concept_code"].tolist()
    toks = [tokenize(n) for n in names]
    inv = {}
    for i, ts in enumerate(toks):
        for t in ts:
            inv.setdefault(t, []).append(i)
    print(f"  {len(names):,} lab-measurement LOINC concepts, {len(inv):,} tokens indexed")
    return names, codes, toks, inv


def match(label, fluid, names, codes, toks, inv):
    """Precision-constrained: a candidate is eligible only if EVERY meaningful label token appears
    in it (so 'Ferritin' can't match a random ferritin-adjacent panel). Rank eligible by Jaccard +
    specimen bonus. Returns (code, name, score, margin) or None."""
    lab_tok = tokenize(label)
    if not lab_tok:
        return None
    hints = FLUID_HINTS.get(str(fluid).lower().strip(), [])
    cand = set()
    for t in lab_tok:
        cand.update(inv.get(t, ()))
    scored = []
    for i in cand:
        ct = toks[i]
        if not lab_tok <= ct:          # require ALL label tokens present in candidate
            continue
        score = len(lab_tok & ct) / len(lab_tok | ct)     # Jaccard
        nl = names[i].lower()
        if hints and any(h in nl for h in hints):
            score += 0.20
        # prefer a quantitative property; nudge down qualitative/ratio forms. Kept small (±0.15) so
        # a urine-dipstick item whose ONLY forms are [Presence] still clears the accept threshold.
        if any(q in nl for q in QUANT_MARK):
            score += 0.15
        if any(q in nl for q in NONQUANT_MARK):
            score -= 0.15
        # ratio concepts ("Albumin in CSF/Albumin in Serum") — but the slash in UNIT notation
        # ("[Mass/volume]") is not a ratio, so strip bracketed unit blocks before checking.
        if "/" in re.sub(r"\[[^\]]*\]", "", names[i]):
            score -= 0.15
        scored.append((score, codes[i], names[i]))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best = scored[0]
    # margin over the next DISTINCT code
    margin = best[0] - next((s for s, c, n in scored[1:] if c != best[1]), 0.0)
    return best[1], best[2], round(best[0], 3), round(margin, 3)


def main():
    curated = json.loads((OUT_DIR / "curated_lab_loinc.json").read_text())
    curated_ids = {int(k) for k in curated}

    used = pd.read_parquet(OUT_DIR / "_used_itemids_cache.parquet")
    d = pd.read_csv(D_LABITEMS, dtype=str); d["itemid"] = d["itemid"].astype("int64")
    used["itemid"] = used["itemid"].astype("int64")
    m = used.merge(d, on="itemid", how="left").sort_values("n_measurements", ascending=False)

    names, codes, toks, inv = load_loinc()

    out = {}
    for r in m.itertuples():
        itemid = int(r.itemid)
        label = r.label if isinstance(r.label, str) else ""
        fluid = r.fluid if isinstance(r.fluid, str) else ""
        n = int(r.n_measurements)
        base = {"itemid": itemid, "mimic_label": label, "fluid": fluid, "n_measurements": n}

        if itemid in curated_ids:
            c = curated[str(itemid)]
            out[itemid] = {**base, "status": "curated",
                           "loinc_code": c["loinc_code"], "loinc_name": c["loinc_name"]}
            continue
        ll = label.strip().lower()
        # specimen-container holds ("Red Top Hold", "EDTA Hold", "Urine tube, held", "Uhold") are
        # not measurements — they record that a tube was retained, no analyte, no value.
        is_hold = ("hold" in ll) or ("held" in ll) or ll.endswith("hold")
        if ll in NON_LAB_EXACT or is_hold:
            out[itemid] = {**base, "status": "non_lab", "loinc_code": None, "loinc_name": None}
            continue
        res = match(label, fluid, names, codes, toks, inv)
        if res and res[2] >= 0.20:
            out[itemid] = {**base, "status": "auto", "loinc_code": res[0], "loinc_name": res[1],
                           "score": res[2], "margin": res[3]}
        else:
            out[itemid] = {**base, "status": "unmapped", "loinc_code": None, "loinc_name": None,
                           "best_guess": (res[1] if res else None)}

    # ---- report ----
    tot_vol = sum(v["n_measurements"] for v in out.values())
    by = {}
    for v in out.values():
        s = v["status"]
        by.setdefault(s, [0, 0])
        by[s][0] += 1
        by[s][1] += v["n_measurements"]
    print(f"\n=== resolution of all {len(out)} itemids ({tot_vol:,} measurements) ===")
    for s in ("curated", "auto", "non_lab", "unmapped"):
        if s in by:
            cnt, vol = by[s]
            print(f"  {s:9s}: {cnt:4d} itemids   {vol:>7,} meas ({100*vol/tot_vol:5.1f}% of volume)")
    mapped_vol = by.get("curated", [0, 0])[1] + by.get("auto", [0, 0])[1]
    print(f"\n  MAPPED to a LOINC code: {100*mapped_vol/tot_vol:.1f}% of volume")
    print(f"  RESOLVED (every itemid has a decision): 100.0%")

    ordered = sorted(out.values(), key=lambda v: -v["n_measurements"])
    (OUT_DIR / "lab_loinc_final.json").write_text(json.dumps(ordered, indent=2))
    print(f"\nwrote {OUT_DIR / 'lab_loinc_final.json'}")

    print("\n--- sample of AUTO matches (top 25 by volume) ---")
    shown = 0
    for v in ordered:
        if v["status"] == "auto":
            print(f"  {v['itemid']:>7} {v['mimic_label'][:32]:32s} -> {v['loinc_code']:9s} "
                  f"{v['loinc_name'][:46]:46s} (s={v['score']},m={v['margin']})")
            shown += 1
            if shown >= 25:
                break

    print("\n--- UNMAPPED real labs (top 25 by volume — candidates for hand-curation) ---")
    shown = 0
    for v in ordered:
        if v["status"] == "unmapped":
            print(f"  {v['itemid']:>7} {v['mimic_label'][:34]:34s} ({v['fluid'][:10]:10s}) "
                  f"n={v['n_measurements']:>4}  guess={v.get('best_guess')}")
            shown += 1
            if shown >= 25:
                break


if __name__ == "__main__":
    main()
