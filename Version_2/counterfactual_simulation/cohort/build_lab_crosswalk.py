"""
build_lab_crosswalk.py — map every lab itemid actually used by cohort_v1 to a LOINC code,
by matching d_labitems' human-readable label against Athena's LOINC concept names.

Step 1: scan labevents.csv.gz once, restricted to cohort_v1's hadm_ids, collect every itemid used
        + how often (so we know which labs actually matter for this cohort, not MIMIC's full catalog).
Step 2: join itemid -> (label, fluid, category) via hosp/d_labitems.csv.gz.
Step 3: for each distinct (label, fluid), score every LOINC row in the downloaded Athena CONCEPT.csv
        by token overlap between d_labitems.label and LOINC concept_name, using fluid as a tiebreaker
        (LOINC names embed the specimen system, e.g. "... in Serum or Plasma" / "... in Blood" /
        "... in Urine"). Output the top candidates per lab, not a silent single guess — some are
        genuinely ambiguous (e.g. multiple specimen types, mass vs. moles units) and need a human look.
"""
from __future__ import annotations

import re
import json
from pathlib import Path

import pandas as pd

MIMIC = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
LABEVENTS = MIMIC / "hosp/labevents.csv.gz"
D_LABITEMS = MIMIC / "hosp/d_labitems.csv.gz"
ATHENA_CONCEPT = Path("/scratch/users/karun09/Version_2/vocabulary_download_v5_"
                      "{e770b936-2d4a-4239-ad97-64ef3269a20d}_1782458474101/CONCEPT.csv")
COHORT = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/cohort/cohort_v1.parquet")
OUT_DIR = Path("/scratch/users/karun09/Version_2/counterfactual_simulation/cohort")

# rough specimen-system synonyms so "Blood" in d_labitems can match "Serum or Plasma" in LOINC names
FLUID_HINTS = {
    "blood": ["serum", "plasma", "blood"],
    "urine": ["urine"],
    "csf": ["cerebral spinal fluid", "csf"],
    "other body fluid": ["body fluid"],
    "ascites": ["ascitic fluid", "peritoneal fluid"],
    "pleural": ["pleural fluid"],
    "joint fluid": ["synovial fluid"],
    "stool": ["stool", "feces"],
}

STOPWORDS = {"in", "of", "the", "a", "on", "by", "panel", "and"}


def tokenize(s) -> set[str]:
    if not isinstance(s, str):
        return set()
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOPWORDS and len(t) > 1}


def scan_used_itemids(hadm_ids: set[int]) -> pd.DataFrame:
    print(f"scanning {LABEVENTS} for itemids used by {len(hadm_ids):,} cohort hadm_ids ...")
    counts: dict[int, int] = {}
    n_rows = 0
    for chunk in pd.read_csv(LABEVENTS, usecols=["hadm_id", "itemid"],
                             dtype={"hadm_id": "float64", "itemid": "int32"}, chunksize=5_000_000):
        n_rows += len(chunk)
        chunk = chunk.dropna(subset=["hadm_id"])
        chunk["hadm_id"] = chunk["hadm_id"].astype("int64")
        chunk = chunk[chunk["hadm_id"].isin(hadm_ids)]
        if len(chunk):
            vc = chunk["itemid"].value_counts()
            for it, n in vc.items():
                counts[it] = counts.get(it, 0) + int(n)
        print(f"  scanned {n_rows:,} rows, {len(counts)} distinct itemids so far", end="\r")
    print()
    return pd.DataFrame([{"itemid": k, "n_measurements": v} for k, v in counts.items()])


def load_loinc_table() -> pd.DataFrame:
    print(f"loading LOINC rows from {ATHENA_CONCEPT} ...")
    loinc_rows = []
    for chunk in pd.read_csv(ATHENA_CONCEPT, sep="\t", usecols=[
            "concept_id", "concept_name", "domain_id", "vocabulary_id",
            "concept_class_id", "standard_concept", "concept_code"],
            dtype=str, chunksize=500_000):
        loinc_rows.append(chunk[chunk["vocabulary_id"] == "LOINC"])
    loinc = pd.concat(loinc_rows, ignore_index=True)
    loinc = loinc[loinc["standard_concept"] == "S"]     # standard (non-deprecated) concepts only
    # HARD filter, not a bonus: LOINC also codes questionnaire answers ("Wheelchair/scooter full
    # time"), survey items, etc. A lab name should never resolve to one of those — restricting to
    # domain=Measurement + class=Lab Test is what excludes them, verified against known-correct
    # codes (e.g. 2823-3 Potassium, 2160-0 Creatinine are both Measurement/Lab Test).
    loinc = loinc[(loinc["domain_id"] == "Measurement") & (loinc["concept_class_id"] == "Lab Test")]
    loinc = loinc.dropna(subset=["concept_name"]).reset_index(drop=True)
    print(f"  {len(loinc):,} standard LOINC concepts loaded")
    loinc["tokens"] = loinc["concept_name"].map(tokenize)
    return loinc


def build_inverted_index(loinc: pd.DataFrame) -> dict[str, list[int]]:
    """token -> list of loinc row indices containing it — avoids comparing every lab against
    all 40k LOINC rows one by one (that brute-force loop is what was timing out)."""
    idx: dict[str, list[int]] = {}
    for i, toks in enumerate(loinc["tokens"]):
        for t in toks:
            idx.setdefault(t, []).append(i)
    return idx


def best_matches(label: str, fluid: str, loinc_lists: dict, inv_idx: dict, top_n: int = 3) -> list[dict]:
    """loinc_lists: plain-Python parallel lists (tokens/concept_name/concept_code/concept_class_id) —
    NOT a DataFrame. Repeated .iloc[i] on a DataFrame inside this loop was the actual hang: some labs'
    tokens match thousands of LOINC rows, and .iloc[] has enough per-call overhead to make that look
    like a stuck process rather than a slow one."""
    label_tokens = tokenize(label)
    fluid_hints = FLUID_HINTS.get(str(fluid).lower().strip(), [])
    candidate_rows = set()
    for t in label_tokens:
        candidate_rows.update(inv_idx.get(t, ()))

    tokens_l, names_l, codes_l, class_l = (loinc_lists["tokens"], loinc_lists["concept_name"],
                                           loinc_lists["concept_code"], loinc_lists["concept_class_id"])
    scores = []
    for i in candidate_rows:
        cand_tokens = tokens_l[i]
        overlap = len(label_tokens & cand_tokens)
        if overlap == 0:
            continue
        # Jaccard, not recall: "Potassium" alone must NOT score 1.0 against a LOINC name with a
        # pile of extra qualifier words ("Voltage-gated potassium channel Ab ...") just because it
        # contains "potassium" too — this is what let a plain lab match an antibody test earlier.
        union = len(label_tokens | cand_tokens)
        score = overlap / union
        if any(h in names_l[i].lower() for h in fluid_hints):
            score += 0.15           # fluid/system match is a disambiguator, not a dominant signal
        scores.append((score, codes_l[i], names_l[i]))
    scores.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for score, code, name in scores:
        if code in seen:
            continue
        seen.add(code)
        out.append({"loinc_code": code, "loinc_name": name, "score": round(score, 3)})
        if len(out) >= top_n:
            break
    return out


def main():
    cohort = pd.read_parquet(COHORT)
    hadm_ids = set(cohort["hadm_id"].astype(int))

    scan_cache = OUT_DIR / "_used_itemids_cache.parquet"
    if scan_cache.exists():
        print(f"reusing cached scan: {scan_cache}")
        used = pd.read_parquet(scan_cache)
    else:
        used = scan_used_itemids(hadm_ids)
        used.to_parquet(scan_cache, index=False)

    d_lab = pd.read_csv(D_LABITEMS, dtype=str)
    d_lab["itemid"] = d_lab["itemid"].astype("int64")
    used["itemid"] = used["itemid"].astype("int64")
    used = used.merge(d_lab, on="itemid", how="left")
    used = used.sort_values("n_measurements", ascending=False)
    print(f"\n{len(used)} distinct lab itemids used by the cohort "
         f"({used['n_measurements'].sum():,} total measurements)")

    loinc = load_loinc_table()
    print("building inverted token index over LOINC names ...")
    inv_idx = build_inverted_index(loinc)
    print(f"  {len(inv_idx):,} distinct tokens indexed")
    loinc_lists = {col: loinc[col].tolist() for col in
                   ("tokens", "concept_name", "concept_code", "concept_class_id")}

    checkpoint = OUT_DIR / "lab_loinc_crosswalk.json"

    def save_checkpoint():
        tmp = checkpoint.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=2))
        tmp.replace(checkpoint)          # atomic — a kill mid-write can't corrupt the real file

    rows = []
    done_itemids = set()
    if checkpoint.exists():
        try:
            rows = json.loads(checkpoint.read_text())
            done_itemids = {r["itemid"] for r in rows}
            print(f"resuming: {len(rows)} labs already matched in a prior run, skipping those")
        except json.JSONDecodeError:
            print("checkpoint was corrupt (killed mid-write) — starting the matching loop over")
            rows, done_itemids = [], set()

    remaining = used[~used["itemid"].isin(done_itemids)]
    for n, r in enumerate(remaining.itertuples()):
        label = r.label if isinstance(r.label, str) else ""
        fluid = r.fluid if isinstance(r.fluid, str) else ""
        cands = best_matches(label, fluid, loinc_lists, inv_idx)
        rows.append({
            "itemid": int(r.itemid), "label": r.label, "fluid": r.fluid, "category": r.category,
            "n_measurements": int(r.n_measurements),
            "top_match": cands[0] if cands else None,
            "alt_matches": cands[1:] if len(cands) > 1 else [],
            # Jaccard scale: a good match is usually ~0.3-0.6 (label tokens are a small subset of a
            # verbose LOINC name by construction), so "confident" is about CLEAR separation from the
            # runner-up, not an absolute score near 1.0 that a short label will rarely reach.
            "confident": bool(cands and cands[0]["score"] >= 0.25 and
                             (len(cands) == 1 or cands[0]["score"] - cands[1]["score"] >= 0.1)),
        })
        if (n + 1) % 25 == 0:
            save_checkpoint()
            print(f"  matched {len(rows)}/{len(used)} labs total (checkpointed)", flush=True)
    save_checkpoint()

    n_confident = sum(1 for r in rows if r["confident"])
    n_nomatch = sum(1 for r in rows if r["top_match"] is None)
    print(f"\n{n_confident}/{len(rows)} labs matched with high confidence; "
         f"{n_nomatch} had no LOINC candidate at all (need a human look)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "lab_loinc_crosswalk.json").write_text(json.dumps(rows, indent=2))
    print(f"wrote {OUT_DIR / 'lab_loinc_crosswalk.json'}")

    print("\n--- top 20 labs by measurement volume ---")
    for r in rows[:20]:
        tm = r["top_match"]
        flag = "OK " if r["confident"] else "?? "
        tm_str = f"{tm['loinc_code']}  {tm['loinc_name']}" if tm else "NO MATCH"
        print(f"{flag}{r['label']:35s} ({r['fluid']:>6s}) n={r['n_measurements']:6d}  -> {tm_str}")

    print("\n--- ambiguous / no-match labs (need review) ---")
    for r in rows:
        if not r["confident"]:
            tm = r["top_match"]
            alts = ", ".join(f"{a['loinc_code']}:{a['score']}" for a in r["alt_matches"][:2])
            tm_str = f"{tm['loinc_code']} {tm['loinc_name']} (score {tm['score']})" if tm else "NO CANDIDATE"
            print(f"  {r['label']} ({r['fluid']}) n={r['n_measurements']}  best={tm_str}  alts=[{alts}]")


if __name__ == "__main__":
    main()
