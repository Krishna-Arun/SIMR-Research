#!/usr/bin/env python3
"""Build a crosswalk from MIMIC-IV ICD codes -> CLMBR-in-vocabulary OMOP standard
concept code-strings, using the local Athena OMOP vocabulary.

MIMIC diagnoses (ICD9CM/ICD10CM) and procedures (ICD9Proc/ICD10PCS) are *source*
(non-standard) concepts. CLMBR-t-base's vocabulary is standard OMOP concepts
(mostly SNOMED for conditions, CPT4/ICD proc for procedures). We therefore:
  source ICD concept  --('Maps to')-->  standard concept  --> "vocab/concept_code"
and keep only code-strings that exist in the CLMBR token vocabulary.

Output: icd_to_clmbr.json  {"9|4280": ["SNOMED/xxxxx", ...], "10|I350": [...], ...}
Key = f"{icd_version}|{icd_code_nodots}".
"""
import csv, json, pickle, sys
from pathlib import Path

REPO = Path("/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research")
COHORT = REPO / "Version_3/Longitudinal/cohort_data"
VOCAB = sorted(REPO.glob("vocabulary_download_v5_*"))[-1]
OUT = Path(__file__).resolve().parent / "meds_build" / "icd_to_clmbr.json"
OUT.parent.mkdir(exist_ok=True)
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

# CLMBR vocab code-strings, read straight from the model tokenizer dictionary.
import femr.models.tokenizer
MODEL = REPO / "Version_3/loaded_models/clmbr-t-base"
_tok = femr.models.tokenizer.FEMRTokenizer.from_pretrained(str(MODEL))
clmbr_codes = {e["code_string"] for e in _tok.dictionary["vocab"] if e.get("code_string")}
print("CLMBR code-strings:", len(clmbr_codes), file=sys.stderr)

import pandas as pd
def nodot(c):
    return str(c).replace(".", "").strip().upper()

# cohort ICD codes we need
diag = pd.read_parquet(COHORT / "diagnoses_icd.parquet")
proc = pd.read_parquet(COHORT / "procedures_icd.parquet")
need = set()   # (vocab_id, nodot_code)
key_by_src = {}  # (vocab_id, nodot_code) -> set of "version|nodot" keys (usually one)
def add(vocab_id, ver, code):
    nd = nodot(code)
    need.add((vocab_id, nd))
    key_by_src.setdefault((vocab_id, nd), set()).add(f"{ver}|{nd}")
for _, r in diag.iterrows():
    add("ICD10CM" if r.icd_version == 10 else "ICD9CM", int(r.icd_version), r.icd_code)
for _, r in proc.iterrows():
    add("ICD10PCS" if r.icd_version == 10 else "ICD9Proc", int(r.icd_version), r.icd_code)
print("distinct source ICD codes needed:", len(need), file=sys.stderr)

WANT_VOCABS = {"ICD10CM", "ICD9CM", "ICD10PCS", "ICD9Proc"}

# Pass 1 over CONCEPT.csv: source concept_id -> our (vocab,nd) key; collect all ids too
src_id_to_srckey = {}          # source concept_id -> (vocab, nd)
concept_id_to_codestr = {}     # any concept_id -> "vocab/concept_code" (for standard lookup pass 3)
print("scanning CONCEPT.csv (pass 1: find source ids)...", file=sys.stderr)
with open(VOCAB / "CONCEPT.csv", newline="") as f:
    rd = csv.reader(f, delimiter="\t")
    header = next(rd)
    ix = {h: i for i, h in enumerate(header)}
    ci, cn, vi, cc = ix["concept_id"], ix["concept_name"], ix["vocabulary_id"], ix["concept_code"]
    for row in rd:
        if len(row) <= cc:
            continue
        vocab_id = row[vi]
        if vocab_id in WANT_VOCABS:
            nd = nodot(row[cc])
            if (vocab_id, nd) in need:
                src_id_to_srckey[int(row[ci])] = (vocab_id, nd)
print("matched source concept_ids:", len(src_id_to_srckey), file=sys.stderr)

# Pass 2 over CONCEPT_RELATIONSHIP.csv: 'Maps to' from source ids -> standard ids
src_ids = set(src_id_to_srckey)
maps = {}  # source_id -> set(standard_id)
std_ids = set()
print("scanning CONCEPT_RELATIONSHIP.csv ('Maps to')...", file=sys.stderr)
with open(VOCAB / "CONCEPT_RELATIONSHIP.csv", newline="") as f:
    rd = csv.reader(f, delimiter="\t")
    header = next(rd)
    ix = {h: i for i, h in enumerate(header)}
    c1, c2, rel = ix["concept_id_1"], ix["concept_id_2"], ix["relationship_id"]
    for row in rd:
        if len(row) <= rel or row[rel] != "Maps to":
            continue
        a = int(row[c1])
        if a in src_ids:
            b = int(row[c2])
            maps.setdefault(a, set()).add(b)
            std_ids.add(b)
print("source ids with 'Maps to':", len(maps), "standard ids:", len(std_ids), file=sys.stderr)

# Pass 3 over CONCEPT.csv: standard id -> "vocab/concept_code"
print("scanning CONCEPT.csv (pass 3: standard code-strings)...", file=sys.stderr)
std_codestr = {}
with open(VOCAB / "CONCEPT.csv", newline="") as f:
    rd = csv.reader(f, delimiter="\t")
    header = next(rd)
    ix = {h: i for i, h in enumerate(header)}
    ci, vi, cc = ix["concept_id"], ix["vocabulary_id"], ix["concept_code"]
    for row in rd:
        if len(row) <= cc:
            continue
        cid = int(row[ci])
        if cid in std_ids:
            std_codestr[cid] = f"{row[vi]}/{row[cc]}"

# Assemble key -> list of in-vocab standard code-strings
result = {}
kept = dropped_oov = 0
for src_id, srckey in src_id_to_srckey.items():
    for k in key_by_src[srckey]:
        for std in maps.get(src_id, ()):
            cs = std_codestr.get(std)
            if cs is None:
                continue
            if cs in clmbr_codes:
                result.setdefault(k, [])
                if cs not in result[k]:
                    result[k].append(cs)
                    kept += 1
            else:
                dropped_oov += 1
OUT.write_text(json.dumps(result, indent=0))
print(f"keys mapped: {len(result)}  code-strings kept: {kept}  dropped (std but OOV for CLMBR): {dropped_oov}", file=sys.stderr)
print("wrote", OUT, file=sys.stderr)
