"""
curated_lab_loinc.py — hand-curated MIMIC itemid -> LOINC for the cohort's high-volume labs,
each VERIFIED against the downloaded Athena CONCEPT.csv (existence + domain=Measurement +
class=Lab Test + the analyte word appears in the official name). Fuzzy matching failed on exactly
these common short-named labs, so the top ~90% of measurement volume is pinned by hand here; the
long tail is left to the fuzzy crosswalk (with its confidence flag).

Specimen convention: MIMIC labels most chemistry fluid="Blood" but they are serum/plasma assays,
so those map to "... in Serum or Plasma" LOINC. Blood-gas panel items are whole-blood/arterial and
map to "... in Blood". Non-physiologic items (Specimen Type, Intubated, hemolysis/icterus/lipemia
indices "H"/"I"/"L", Temperature) are intentionally left unmapped — they are not lab analytes.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import pandas as pd

ATHENA_CONCEPT = Path("/scratch/users/karun09/Version_2/vocabulary_download_v5_"
                      "{e770b936-2d4a-4239-ad97-64ef3269a20d}_1782458474101/CONCEPT.csv")
OUT_DIR = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/cohort")

# itemid -> (expected analyte keyword for the sanity check, LOINC code)
CURATED = {
    # ---- Chemistry (serum/plasma) ----
    50971: ("potassium",   "2823-3"),
    50983: ("sodium",      "2951-2"),
    50902: ("chloride",    "2075-0"),
    50912: ("creatinine",  "2160-0"),
    51006: ("urea",        "3094-0"),
    50882: ("bicarbonate", "1963-8"),
    50868: ("anion",       "1863-0"),
    50960: ("magnesium",   "2601-3"),
    50931: ("glucose",     "2345-7"),
    50970: ("phosphate",   "2777-1"),
    50893: ("calcium",     "17861-6"),
    50920: ("glomerular",  "33914-3"),
    51003: ("troponin",    "6598-7"),
    50911: ("creatine",    "13969-1"),   # CK-MB
    50910: ("creatine",    "2157-6"),    # CK total
    50885: ("bilirubin",   "1975-2"),
    50861: ("alanine",     "1742-6"),    # ALT
    50878: ("aspartate",   "1920-8"),    # AST
    50863: ("alkaline",    "6768-6"),
    50954: ("lactate",     "2532-0"),    # LDH
    # ---- Hematology (CBC) ----
    51221: ("hematocrit",  "4544-3"),
    51222: ("hemoglobin",  "718-7"),
    51265: ("platelets",   "777-3"),
    51301: ("leukocytes",  "6690-2"),    # WBC
    51279: ("erythrocytes","789-8"),     # RBC
    51250: ("mcv",         "787-2"),
    51248: ("mch",         "785-6"),
    51249: ("mchc",        "786-4"),
    51277: ("erythrocyte", "788-0"),     # RDW-CV
    52172: ("erythrocyte", "21000-5"),   # RDW-SD
    51275: ("aptt",        "3173-2"),    # PTT
    51237: ("inr",         "34714-6"),
    51274: ("prothrombin", "5902-2"),    # PT
    # ---- Differential (%) ----
    51244: ("lymphocytes", "736-9"),
    51254: ("monocytes",   "5905-5"),
    51200: ("eosinophils", "713-8"),
    51256: ("neutrophils", "770-8"),
    51146: ("basophils",   "706-2"),
    # ---- Blood gas (whole blood / arterial) ----
    50820: ("ph",          "11558-4"),
    50821: ("oxygen",      "11556-8"),   # pO2
    50818: ("carbon",      "11557-6"),   # pCO2
    50802: ("base",        "11555-0"),   # base excess
    50804: ("carbon",      "34728-6"),   # total CO2
    50813: ("lactate",     "32693-4"),
    50817: ("oxygen",      "20564-1"),   # O2 sat
    50808: ("calcium",     "1994-3"),    # free/ionized calcium
    50822: ("potassium",   "6298-4"),    # K whole blood
    50809: ("glucose",     "2339-0"),    # glucose whole blood
    50811: ("hemoglobin",  "718-7"),
    50810: ("hematocrit",  "4544-3"),
    # ---- Urine ----
    51478: ("glucose",     "5792-7"),
    51498: ("specific",    "5811-5"),
    51484: ("ketones",     "5797-6"),
    # ---- second batch: labs whose MIMIC wording differs from LOINC's, or auto-matched wrong ----
    50993: ("thyrotropin", "3016-3"),    # TSH -> LOINC "Thyrotropin"
    50963: ("natriuretic", "33762-6"),   # NTproBNP
    50986: ("tacrolimus",  "11253-2"),   # tacroFK
    51007: ("urate",       "3084-1"),    # Uric Acid -> LOINC "Urate"
    50964: ("osmolality",  "2692-2"),    # Osmolality, measured (serum)
    51000: ("triglyceride","2571-8"),
    50907: ("cholesterol", "2093-3"),    # total cholesterol
    50904: ("cholesterol", "2085-9"),    # HDL
    50905: ("cholesterol", "13457-7"),   # LDL calculated
    50924: ("ferritin",    "2276-4"),
    50952: ("iron",        "2498-4"),
    50867: ("amylase",     "1798-8"),
    50862: ("albumin",     "1751-7"),    # serum albumin (auto picked an immunoassay variant)
    51133: ("lymphocytes", "731-0"),     # Absolute Lymphocyte (auto picked "B lymphocytes")
    52073: ("eosinophils", "26449-9"),
    52069: ("basophils",   "704-7"),
    52074: ("monocytes",   "742-7"),
    52075: ("neutrophils", "751-8"),
    51082: ("creatinine",  "2161-8"),    # Creatinine, Urine (mass/vol)
    51104: ("urea",        "3095-7"),    # Urea nitrogen, Urine (mass/vol)
}


def load_loinc_by_code() -> dict:
    print("loading LOINC concepts from Athena ...")
    keep = {}
    # OMOP exports are tab-delimited with NO quoting; chemical names contain stray ' and " that
    # break pandas' default parser and silently drop ~half the LOINC rows. QUOTE_NONE fixes it.
    for chunk in pd.read_csv(ATHENA_CONCEPT, sep="\t", quoting=csv.QUOTE_NONE, usecols=[
            "concept_id", "concept_name", "domain_id", "vocabulary_id",
            "concept_class_id", "standard_concept", "concept_code"],
            dtype=str, chunksize=500_000):
        c = chunk[chunk["vocabulary_id"] == "LOINC"]
        for r in c.itertuples():
            keep[r.concept_code] = (r.concept_name, r.domain_id, r.concept_class_id,
                                    r.standard_concept, r.concept_id)
    print(f"  {len(keep):,} LOINC codes indexed")
    return keep


def main():
    lo = load_loinc_by_code()
    used = pd.read_parquet(OUT_DIR / "_used_itemids_cache.parquet")
    d = pd.read_csv("/scratch/users/karun09/physionet.org/files/mimiciv/3.1/hosp/d_labitems.csv.gz", dtype=str)
    d["itemid"] = d["itemid"].astype("int64")
    labels = dict(zip(d["itemid"], d["label"]))
    nmeas = dict(zip(used["itemid"].astype(int), used["n_measurements"]))

    verified, problems = {}, []
    print("\n--- verification (itemid -> LOINC, official Athena name) ---")
    for itemid, (kw, code) in CURATED.items():
        entry = lo.get(code)
        label = labels.get(itemid, "?")
        if entry is None:
            problems.append((itemid, label, code, "CODE NOT IN ATHENA"))
            print(f"  !! {itemid} {label:28s} {code:9s} -> NOT FOUND")
            continue
        name, domain, cls, std, cid = entry
        # O2 saturation and a few calculated values are filed as "Clinical Observation" not
        # "Lab Test" in OMOP, but are still the correct Measurement concept — accept both classes.
        ok_domain = (domain == "Measurement" and cls in ("Lab Test", "Clinical Observation"))
        ok_kw = kw.lower() in name.lower()
        flag = "OK " if (ok_domain and ok_kw) else "?? "
        if not (ok_domain and ok_kw):
            problems.append((itemid, label, code, f"domain={domain}/{cls} kw_match={ok_kw} :: {name}"))
        verified[str(itemid)] = {"itemid": itemid, "mimic_label": label,
                                 "n_measurements": int(nmeas.get(itemid, 0)),
                                 "loinc_code": code, "loinc_name": name,
                                 "omop_concept_id": cid, "verified": bool(ok_domain and ok_kw)}
        print(f"  {flag}{itemid} {str(label)[:26]:26s} {code:9s} -> {name}")

    n_ok = sum(1 for v in verified.values() if v["verified"])
    vol_ok = sum(v["n_measurements"] for v in verified.values() if v["verified"])
    tot_vol = sum(nmeas.values())
    print(f"\n{n_ok}/{len(CURATED)} curated codes verified clean; "
          f"they cover {vol_ok:,}/{tot_vol:,} = {100*vol_ok/tot_vol:.1f}% of all cohort lab volume")
    if problems:
        print(f"\n{len(problems)} need attention:")
        for it, lab, code, why in problems:
            print(f"  {it} {lab} [{code}]: {why}")

    (OUT_DIR / "curated_lab_loinc.json").write_text(json.dumps(verified, indent=2))
    print(f"\nwrote {OUT_DIR / 'curated_lab_loinc.json'}")


if __name__ == "__main__":
    main()
