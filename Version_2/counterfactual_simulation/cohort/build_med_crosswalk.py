"""
build_med_crosswalk.py — map the cohort's medications to RxNorm (the vocab CLMBR knows).

MIMIC prescriptions carry an 11-digit NDC. RxNorm is what CLMBR was trained on. Athena has both
NDC and RxNorm plus the "Maps to" edges between them, so the chain is:

    MIMIC ndc (11-digit) -> Athena NDC concept -> [Maps to] -> RxNorm concept

Fallback for rows whose ndc is 0/missing/unmapped: match the drug NAME against RxNorm Ingredient
names. Coarsest fallback (not built here, noted): ATC therapeutic class.

Reads Athena with quoting=QUOTE_NONE (the default parser silently drops rows on stray ' / ").
Every step reports coverage by PRESCRIPTION VOLUME so we know exactly what reached RxNorm.
"""
from __future__ import annotations

import csv
import re
import json
from pathlib import Path
import pandas as pd

MIMIC = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
PRESC = MIMIC / "hosp/prescriptions.csv.gz"
V = Path("/scratch/users/karun09/Version_2/vocabulary_download_v5_"
         "{e770b936-2d4a-4239-ad97-64ef3269a20d}_1782458474101")
CONCEPT = V / "CONCEPT.csv"
REL = V / "CONCEPT_RELATIONSHIP.csv"
OUT = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/cohort")


def norm_ndc(x) -> str:
    """MIMIC ndc -> 11-digit zero-padded string; '' for missing/zero."""
    if not isinstance(x, str):
        x = "" if pd.isna(x) else str(x)
    d = re.sub(r"\D", "", x)
    if not d or int(d or 0) == 0:
        return ""
    return d.zfill(11)[-11:]


def scan_prescriptions(hadm_ids: set) -> pd.DataFrame:
    cache = OUT / "_used_meds_cache.parquet"
    if cache.exists():
        print(f"reusing cached prescription scan: {cache}")
        return pd.read_parquet(cache)
    print(f"scanning {PRESC} for {len(hadm_ids):,} cohort hadm_ids ...")
    rows, n = {}, 0
    for chunk in pd.read_csv(PRESC, usecols=["hadm_id", "drug", "gsn", "ndc"],
                             dtype=str, chunksize=2_000_000):
        n += len(chunk)
        chunk = chunk.dropna(subset=["hadm_id"])
        chunk["hadm_id"] = pd.to_numeric(chunk["hadm_id"], errors="coerce")
        chunk = chunk[chunk["hadm_id"].isin(hadm_ids)]
        for r in chunk.itertuples():
            key = (norm_ndc(r.ndc), str(r.drug))
            rows[key] = rows.get(key, 0) + 1
        print(f"  scanned {n:,} rows, {len(rows):,} distinct (ndc,drug) so far", end="\r")
    print()
    df = pd.DataFrame([{"ndc": k[0], "drug": k[1], "n": v} for k, v in rows.items()])
    df.to_parquet(cache, index=False)
    return df


def load_ndc_concepts(needed: set) -> dict:
    """11-digit ndc string -> Athena concept_id, for NDCs the cohort actually uses."""
    print("loading Athena NDC concepts ...")
    out = {}
    for ch in pd.read_csv(CONCEPT, sep="\t", quoting=csv.QUOTE_NONE,
                          usecols=["concept_id", "vocabulary_id", "concept_code"],
                          dtype=str, chunksize=500_000):
        ndc = ch[ch["vocabulary_id"] == "NDC"]
        for r in ndc.itertuples():
            code = norm_ndc(r.concept_code)
            if code in needed:
                out[code] = r.concept_id
    print(f"  matched {len(out):,}/{len(needed):,} cohort NDCs to an Athena concept")
    return out


def load_maps_to(src_ids: set) -> dict:
    """concept_id(NDC) -> concept_id(target standard) via 'Maps to'."""
    print("streaming CONCEPT_RELATIONSHIP for 'Maps to' edges ...")
    out, n = {}, 0
    for ch in pd.read_csv(REL, sep="\t", quoting=csv.QUOTE_NONE,
                          usecols=["concept_id_1", "concept_id_2", "relationship_id"],
                          dtype=str, chunksize=2_000_000):
        n += len(ch)
        m = ch[(ch["relationship_id"] == "Maps to") & (ch["concept_id_1"].isin(src_ids))]
        for r in m.itertuples():
            out[r.concept_id_1] = r.concept_id_2
        print(f"  scanned {n:,} rel rows, {len(out):,} NDC->target edges", end="\r")
    print()
    return out


def load_concept_info(ids: set) -> dict:
    """concept_id -> (name, code, vocab, class) for target concepts."""
    print("loading target concept info ...")
    out = {}
    for ch in pd.read_csv(CONCEPT, sep="\t", quoting=csv.QUOTE_NONE,
                          usecols=["concept_id", "concept_name", "concept_code",
                                   "vocabulary_id", "concept_class_id"],
                          dtype=str, chunksize=500_000):
        m = ch[ch["concept_id"].isin(ids)]
        for r in m.itertuples():
            out[r.concept_id] = (r.concept_name, r.concept_code, r.vocabulary_id, r.concept_class_id)
    return out


def load_rxnorm_ingredients() -> dict:
    """lowercased ingredient name -> (concept_code, concept_name) for the name fallback."""
    print("loading RxNorm ingredients for name fallback ...")
    out = {}
    for ch in pd.read_csv(CONCEPT, sep="\t", quoting=csv.QUOTE_NONE,
                          usecols=["concept_name", "vocabulary_id", "concept_class_id",
                                   "standard_concept", "concept_code"],
                          dtype=str, chunksize=500_000):
        ing = ch[(ch["vocabulary_id"].isin(["RxNorm", "RxNorm Extension"])) &
                 (ch["concept_class_id"] == "Ingredient") & (ch["standard_concept"] == "S")]
        for r in ing.itertuples():
            out[r.concept_name.lower()] = (r.concept_code, r.concept_name)
    print(f"  {len(out):,} RxNorm ingredients")
    return out


def main():
    cohort = pd.read_parquet(OUT / "cohort_v1.parquet")
    hadm = set(pd.to_numeric(cohort["hadm_id"]).astype(int))
    meds = scan_prescriptions(hadm).sort_values("n", ascending=False)
    tot = int(meds["n"].sum())
    with_ndc = meds[meds["ndc"] != ""]
    print(f"\n{len(meds):,} distinct (ndc,drug); {tot:,} prescription rows")
    print(f"  rows with a usable NDC: {int(with_ndc['n'].sum()):,} "
          f"({100*with_ndc['n'].sum()/tot:.1f}% of volume)")

    needed_ndc = set(with_ndc["ndc"])
    ndc2cid = load_ndc_concepts(needed_ndc)
    maps = load_maps_to(set(ndc2cid.values()))
    tgt_info = load_concept_info(set(maps.values()))
    ingredients = load_rxnorm_ingredients()

    resolved = {}
    for r in meds.itertuples():
        rec = {"ndc": r.ndc, "drug": r.drug, "n": int(r.n)}
        cid = ndc2cid.get(r.ndc) if r.ndc else None
        tgt = maps.get(cid) if cid else None
        info = tgt_info.get(tgt) if tgt else None
        if info:
            rec.update(status="ndc", rxnorm_code=info[1], rxnorm_name=info[0],
                       vocab=info[2], cls=info[3])
        else:
            hit = ingredients.get(str(r.drug).lower().strip())
            if hit:
                rec.update(status="name", rxnorm_code=hit[0], rxnorm_name=hit[1])
            else:
                rec.update(status="unmapped", rxnorm_code=None, rxnorm_name=None)
        resolved[f"{r.ndc}|{r.drug}"] = rec

    vol = {"ndc": 0, "name": 0, "unmapped": 0}
    for v in resolved.values():
        vol[v["status"]] += v["n"]
    print(f"\n=== medication resolution ({tot:,} prescription rows) ===")
    for s in ("ndc", "name", "unmapped"):
        print(f"  {s:9s}: {vol[s]:>8,} rows ({100*vol[s]/tot:5.1f}%)")
    mapped = vol["ndc"] + vol["name"]
    print(f"\n  MAPPED to RxNorm: {100*mapped/tot:.1f}% of prescription volume")

    (OUT / "med_rxnorm_crosswalk.json").write_text(
        json.dumps(sorted(resolved.values(), key=lambda v: -v["n"]), indent=2))
    print(f"wrote {OUT / 'med_rxnorm_crosswalk.json'}")

    ordered = sorted(resolved.values(), key=lambda v: -v["n"])
    print("\n--- top 20 mapped ---")
    for v in [x for x in ordered if x["status"] != "unmapped"][:20]:
        print(f"  {v['drug'][:30]:30s} n={v['n']:>5} -> [{v['status']}] {v['rxnorm_code']:>10} {v['rxnorm_name'][:34]}")
    print("\n--- top 15 UNMAPPED (by volume) ---")
    for v in [x for x in ordered if x["status"] == "unmapped"][:15]:
        print(f"  {v['drug'][:34]:34s} n={v['n']:>5}  ndc={v['ndc'] or 'none'}")


if __name__ == "__main__":
    main()
