"""Make a downloaded Athena OMOP vocabulary femr-compatible.

Two fixes femr's ontology loader needs but doesn't do itself:
  1. CONCEPT.csv contains unescaped double-quotes in free-text concept_name -> polars CSV parse
     error. We strip stray quotes (descriptions are cosmetic; we use codes + hierarchy only).
  2. CONCEPT_RELATIONSHIP.csv / CONCEPT_ANCESTOR.csv reference concept_ids OUTSIDE the downloaded
     vocabularies (Athena ships cross-vocab edges), but femr assumes every referenced id is present
     in CONCEPT.csv and KeyErrors otherwise. We filter both edge tables to the downloaded concept set
     (dropping edges to absent concepts, which are unusable anyway).

Output: a femr-ready dir at data.athena_path (config). Run in the clmbr311 venv:
    python preprocessing/prepare_athena.py configs/default.yaml
"""
from __future__ import annotations

import os
import sys

import polars as pl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.common import load_config, get_logger

log = get_logger("prepare_athena")


def clean_concept(src: str, dst: str):
    """Stream-strip double-quotes from CONCEPT.csv (preserves tabs/newlines/row count)."""
    n = 0
    with open(src, "r", encoding="utf-8", errors="replace") as f, open(dst, "w", encoding="utf-8") as g:
        for line in f:
            g.write(line.replace('"', ""))
            n += 1
    log.info("cleaned CONCEPT.csv -> %s (%d lines)", dst, n)


def filter_edges(src: str, dst: str, id_cols, concept_ids: pl.Series):
    """Keep only rows whose id columns are all in the downloaded concept set; write tab-sep."""
    lf = pl.scan_csv(src, separator="\t", infer_schema_length=0, quote_char=None)
    ids = pl.LazyFrame({"_cid": concept_ids})
    for col in id_cols:
        lf = lf.join(ids.rename({"_cid": col}), on=col, how="semi")
    out = lf.collect(streaming=True)
    out.write_csv(dst, separator="\t", quote_style="never")
    log.info("filtered %s -> %s (%d rows)", os.path.basename(src), dst, len(out))


def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "configs/default.yaml")
    raw = cfg["data"]["athena_raw"]
    out = cfg["data"]["athena_path"]
    os.makedirs(out, exist_ok=True)

    clean_concept(os.path.join(raw, "CONCEPT.csv"), os.path.join(out, "CONCEPT.csv"))

    concept_ids = (pl.scan_csv(os.path.join(out, "CONCEPT.csv"), separator="\t",
                               infer_schema_length=0, quote_char=None)
                   .select(pl.col("concept_id")).unique().collect()["concept_id"])
    log.info("downloaded concept set: %d ids", len(concept_ids))

    filter_edges(os.path.join(raw, "CONCEPT_RELATIONSHIP.csv"),
                 os.path.join(out, "CONCEPT_RELATIONSHIP.csv"),
                 ["concept_id_1", "concept_id_2"], concept_ids)
    filter_edges(os.path.join(raw, "CONCEPT_ANCESTOR.csv"),
                 os.path.join(out, "CONCEPT_ANCESTOR.csv"),
                 ["ancestor_concept_id", "descendant_concept_id"], concept_ids)
    log.info("ATHENA_READY: %s", out)


if __name__ == "__main__":
    main()
