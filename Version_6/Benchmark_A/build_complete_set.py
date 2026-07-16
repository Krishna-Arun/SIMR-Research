#!/usr/bin/env python3
"""
Build the COMPLETE-SET backbone for Benchmark A.

A "complete set" = a matched pair from Benchmark C whose BOTH members also qualify
for Benchmark B (all-4-lab eligible) and are present in Benchmark A's index
(anchor > 24h). Those pairs are the patients that can carry a coherent A -> B -> C
chain on both arms.

Emits, in interleaved (dialysis, diuresis, ...) order so none-of-above stays
balanced across arms:
  complete_set_case_ids.txt   one Benchmark-A case_id per line
  complete_set_pairs.json     pair_id -> {dialysis_case_id, diuresis_case_id, hadms}
"""
import json, ast, os

HERE = os.path.dirname(os.path.abspath(__file__))
V6 = os.path.dirname(HERE)

# Benchmark C pairs
pairs = {}
for l in open(f"{V6}/Benchmark_C/cases_c.jsonl"):
    it = json.loads(l)
    m = ast.literal_eval(it["meta"]) if isinstance(it["meta"], str) else it["meta"]
    pairs[it["pair_id"]] = (str(m["dialysis_hadm"]), str(m["diuresis_hadm"]))

# Benchmark B eligibility (all-4 labs)
b_dial = set(json.loads(l)["hadm_id"] for l in open(f"{V6}/Benchmark_B/cases_eligible_all4.jsonl"))
b_diur = set(json.loads(l)["hadm_id"] for l in open(f"{V6}/Benchmark_B_diuretic/cases_eligible_all4.jsonl"))

# Benchmark A index (anchor > 24h)
idx = json.load(open(f"{HERE}/index/cases_index.json"))
a_dial = {str(e["hadm_id"]): cid for cid, e in idx.items() if e["cohort"] == "dialysis"}
a_diur = {str(e["hadm_id"]): cid for cid, e in idx.items() if e["cohort"] == "diuretic"}

case_ids = []
pair_map = {}
for pid, (dh, uh) in pairs.items():
    if dh in b_dial and dh in a_dial and uh in b_diur and uh in a_diur:
        d_cid, u_cid = a_dial[dh], a_diur[uh]
        case_ids += [d_cid, u_cid]                      # interleave arms
        pair_map[pid] = {"dialysis_case_id": d_cid, "diuresis_case_id": u_cid,
                         "dialysis_hadm": dh, "diuresis_hadm": uh}

with open(f"{HERE}/complete_set_case_ids.txt", "w") as f:
    f.write("\n".join(case_ids) + "\n")
json.dump(pair_map, open(f"{HERE}/complete_set_pairs.json", "w"), indent=1)

print(f"complete pairs (both arms qualify A+B+C): {len(pair_map)}")
print(f"backbone case_ids written: {len(case_ids)}  "
      f"({sum(1 for c in case_ids if c.startswith('dialysis'))} dialysis / "
      f"{sum(1 for c in case_ids if c.startswith('diuretic'))} diuretic)")
print(f"wrote {HERE}/complete_set_case_ids.txt")
print(f"wrote {HERE}/complete_set_pairs.json")
