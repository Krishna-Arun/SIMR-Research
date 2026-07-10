#!/usr/bin/env python3
"""
extract_anatomy.py — parse coronary anatomy from free-text cath reports (the CATH field
of the cardiac extension) into the structured effect-modifier the individual model was
missing.

Per report we extract:
  n_vessel_disease   : 1/2/3 (from '...vessel disease' phrasing; else count vessels ≥50%)
  lm_stenosis        : left-main % (occlusion -> 100)
  lad/lcx/rca_stenosis: max % stenosis near each vessel mention (occlusion -> 100)
  max_stenosis       : worst lesion overall
  lm_disease         : left-main ≥50%
  total_occlusion    : any 'occluded/occlusion' present
  cabg_recommended   : report recommends CABG

Regex-first (transparent, fast); an LLM pass can refine ambiguous reports later.
Output: cad_anatomy.parquet keyed by hadm_id.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

EXT = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/mimic-iv-ext-cardiac-disease-1.0.0")
OUT = Path(__file__).resolve().parent / "cad_anatomy.parquet"

VESSELS = {"lad": ["LAD", "LEFT ANTERIOR DESCENDING"],
           "lcx": ["LCX", "CIRCUMFLEX", "LCC", "LEFT CIRCUMFLEX"],
           "rca": ["RCA", "RIGHT CORONARY"],
           "lm":  ["LMCA", "LEFT MAIN", "LEFT MAINSTEM"]}
WORD_N = {"ONE": 1, "SINGLE": 1, "TWO": 2, "DOUBLE": 2, "THREE": 3, "TRIPLE": 3}
PCT = re.compile(r"(\d{1,3})\s*%")


def vessel_stenosis(text, terms):
    """Max stenosis % in SENTENCES that mention the vessel (sentence-level attribution,
    so a neighbouring vessel's '80%' doesn't leak onto this one); occlusion -> 100.
    Returns None if the vessel is not mentioned at all."""
    up = text.upper()
    sentences = re.split(r"[.\n;]", up)
    best = None
    mentioned = False
    for s in sentences:
        if not any(re.search(r"\b" + re.escape(t) + r"\b", s) for t in terms):
            continue
        mentioned = True
        if re.search(r"NO\s+(OBSTRUCTIVE|SIGNIFICANT|ANGIOGRAPHIC|CRITICAL)?\s*(DISEASE|STENOSIS|LESION)", s):
            best = max(best or 0, 0)                          # explicitly clean
        if re.search(r"OCCLU", s):
            best = max(best or 0, 100)
        for p in PCT.findall(s):
            v = int(p)
            if 0 <= v <= 100:
                best = max(best or 0, v)
    return best if mentioned else None


def extract(text):
    up = text.upper()
    sten = {v: vessel_stenosis(text, terms) for v, terms in VESSELS.items()}
    # n-vessel disease from phrasing
    nvd = None
    m = re.search(r"\b(ONE|TWO|THREE|SINGLE|DOUBLE|TRIPLE)[\s-]+VESSEL", up)
    if m:
        nvd = WORD_N[m.group(1)]
    if nvd is None:                                          # fallback: count vessels >=50%
        nvd = sum(1 for v in ("lad", "lcx", "rca") if (sten[v] or 0) >= 50)
    vals = [sten[v] or 0 for v in sten]
    return {"n_vessel_disease": nvd,
            "lm_stenosis": sten["lm"] or 0, "lad_stenosis": sten["lad"] or 0,
            "lcx_stenosis": sten["lcx"] or 0, "rca_stenosis": sten["rca"] or 0,
            "max_stenosis": max(vals) if vals else 0,
            "lm_disease": int((sten["lm"] or 0) >= 50),
            "total_occlusion": int(bool(re.search(r"OCCLU", up))),
            "cabg_recommended": int("CABG" in up),
            "anatomy_available": 1}


def main():
    n = pd.read_csv(EXT / "heart_diagnoses.csv", dtype=str)
    cath = n[n.CATH.fillna("").str.len() > 20][["hadm_id", "CATH"]].copy()
    cath["hadm_id"] = cath.hadm_id.str.split(".").str[0].astype("int64")
    print(f"[anatomy] parsing {len(cath):,} cath reports …")
    feats = cath.CATH.map(extract).apply(pd.Series)
    out = pd.concat([cath[["hadm_id"]].reset_index(drop=True), feats.reset_index(drop=True)], axis=1)
    out = out.groupby("hadm_id", as_index=False).max()       # one row per admission
    out.to_parquet(OUT)
    print(f"[anatomy] extracted -> {OUT.name}  ({len(out):,} admissions)")
    print("\n[anatomy] distributions:")
    print("  n_vessel_disease:", out.n_vessel_disease.value_counts().sort_index().to_dict())
    for c in ["lm_disease", "total_occlusion", "cabg_recommended"]:
        print(f"  {c}: {int(out[c].sum())} ({100*out[c].mean():.0f}%)")
    print("  median max_stenosis:", int(out.max_stenosis.median()),
          "| median LAD:", int(out.lad_stenosis.median()), "RCA:", int(out.rca_stenosis.median()))
    # spot-check a couple
    print("\n[anatomy] spot check (first 2 reports):")
    for i in range(2):
        print("  text:", cath.CATH.iloc[i][:150].replace("\n", " "))
        print("  ->", {k: v for k, v in extract(cath.CATH.iloc[i]).items() if k != "anatomy_available"})


if __name__ == "__main__":
    main()
