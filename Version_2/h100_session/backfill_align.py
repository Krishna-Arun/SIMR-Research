"""One-off alignment backfill (no full cohort rebuild):
  1. Re-filter each benchmark's pool to exclude age >= 89 (MIMIC 91 sentinel for 90+).
  2. Materialize microbiology + medication slices for the surviving pool admissions:
       A: outputs/eligible_meds.parquet              (micro already present)
       B: outputs/micro.parquet, outputs/meds.parquet
       C: outputs/micro.parquet, outputs/meds.parquet (for both patients in each surviving pair)
microbiologyevents + prescriptions are each scanned ONCE for the union of needed hadm_ids.
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path("/scratch/users/karun09/physionet.org/files/mimiciv/3.1")
V2 = Path("/scratch/users/karun09/Version_2")
A = V2/"Benchmark_A/Question_Generation/outputs"
B = V2/"Benchmark_B/Question_Generation/outputs"
C = V2/"Benchmark_C/Question_Generation/outputs"

def gz(sub, tbl):
    p = ROOT/sub/f"{tbl}.csv.gz"
    return p if p.exists() else ROOT/sub/f"{tbl}.csv"

print("loading patients ages ...", flush=True)
pat = pd.read_csv(gz("hosp","patients"), usecols=["subject_id","anchor_age"]).set_index("subject_id")
young = set(pat.index[pat["anchor_age"] < 89].astype(int))   # subjects under 89
def subj_ok(s):
    try: return int(s) in young
    except Exception: return False

# ---------- A: pool keyed by hadm_id ----------
a_idx = pd.read_parquet(A/"eligible_index.parquet")[["hadm_id","subject_id"]]
h2s_A = dict(zip(a_idx["hadm_id"].astype(int), a_idx["subject_id"].astype(int)))
a_pool = pd.read_parquet(A/"pool.parquet")
before = len(a_pool)
a_pool = a_pool[a_pool["hadm_id"].astype(int).map(lambda h: subj_ok(h2s_A.get(int(h))))].reset_index(drop=True)
a_pool.to_parquet(A/"pool.parquet", index=False)
A_hadms = set(a_pool["hadm_id"].astype(int))
print(f"A pool: {before} -> {len(a_pool)} (age<89)", flush=True)

# ---------- B: pool keyed by proc_uid ----------
b_idx = pd.read_parquet(B/"eligible_index.parquet")[["proc_uid","hadm_id","subject_id"]]
pu2hs_B = {r.proc_uid:(int(r.hadm_id),int(r.subject_id)) for r in b_idx.itertuples()}
b_pool = pd.read_parquet(B/"pool.parquet")
before = len(b_pool)
b_pool = b_pool[b_pool["proc_uid"].map(lambda u: pu2hs_B.get(u) is not None and subj_ok(pu2hs_B[u][1]))].reset_index(drop=True)
b_pool.to_parquet(B/"pool.parquet", index=False)
B_hadms = set(int(pu2hs_B[u][0]) for u in b_pool["proc_uid"])
print(f"B pool: {before} -> {len(b_pool)} (age<89)", flush=True)

# ---------- C: pool = matched_pairs (drop pair if EITHER patient >=89) ----------
mp = pd.read_parquet(C/"matched_pairs.parquet")
before = len(mp)
def pair_ok(row):
    # resolve subjects via B's eligible_index (C reuses B)
    a = pu2hs_B.get(row["proc_uidA"]); b = pu2hs_B.get(row["proc_uidB"])
    return a is not None and b is not None and subj_ok(a[1]) and subj_ok(b[1])
mask = mp.apply(pair_ok, axis=1)
mp = mp[mask]
mp.to_parquet(C/"matched_pairs.parquet")
C_hadms = set()
for r in mp.itertuples():
    C_hadms.add(int(pu2hs_B[r.proc_uidA][0])); C_hadms.add(int(pu2hs_B[r.proc_uidB][0]))
print(f"C pairs: {before} -> {len(mp)} (age<89 both)", flush=True)

NEED = A_hadms | B_hadms | C_hadms
print(f"union hadms needing micro+meds: {len(NEED)}", flush=True)

# ---------- micro (one scan) ----------
print("scanning microbiologyevents ...", flush=True)
mcols = ["hadm_id","charttime","chartdate","spec_type_desc","test_name","org_name","ab_name","interpretation"]
micro = pd.read_csv(gz("hosp","microbiologyevents"), usecols=mcols, low_memory=False)
micro = micro.dropna(subset=["hadm_id"]); micro["hadm_id"] = micro["hadm_id"].astype("int64")
micro = micro[micro["hadm_id"].isin(NEED)]
micro["charttime"] = pd.to_datetime(micro["charttime"].fillna(micro["chartdate"]), errors="coerce")
def write_micro(hset, path):
    sub = micro[micro["hadm_id"].isin(hset)].sort_values("hadm_id").reset_index(drop=True)
    sub.to_parquet(path, index=False); print(f"  wrote {path.name}: {len(sub)} rows", flush=True)
write_micro(B_hadms, B/"micro.parquet")
write_micro(C_hadms, C/"micro.parquet")
# A already has eligible_micro.parquet from cohort build

# ---------- meds (one chunked scan of prescriptions) ----------
print("scanning prescriptions (chunked) ...", flush=True)
pcols = ["hadm_id","starttime","drug","route"]
parts = []
for i, ch in enumerate(pd.read_csv(gz("hosp","prescriptions"), usecols=pcols,
                                   chunksize=2_000_000, low_memory=False)):
    ch = ch.dropna(subset=["hadm_id"]); ch["hadm_id"] = ch["hadm_id"].astype("int64")
    ch = ch[ch["hadm_id"].isin(NEED)]
    if len(ch): parts.append(ch)
    print(f"  prescriptions chunk {i}", flush=True)
meds = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=pcols)
meds["starttime"] = pd.to_datetime(meds["starttime"], errors="coerce")
def write_meds(hset, path):
    sub = meds[meds["hadm_id"].isin(hset)].sort_values("hadm_id").reset_index(drop=True)
    sub.to_parquet(path, index=False); print(f"  wrote {path.name}: {len(sub)} rows", flush=True)
write_meds(A_hadms, A/"eligible_meds.parquet")
write_meds(B_hadms, B/"meds.parquet")
write_meds(C_hadms, C/"meds.parquet")
print("BACKFILL_DONE", flush=True)
