#!/usr/bin/env python3
"""Benchmark B feasibility, STRICT: dialysis session must occur during an
acute-HF admission. Counts, for all four BMP targets, how many acute-HF
admissions have >=N measurements in 48h pre / 72h post the first dialysis
session of that admission."""
import csv, datetime as dt
from collections import defaultdict

BASE = "/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/Version_6"
PRE_H, POST_H = 48, 72
LABS = ["creat", "bun", "k", "hco3"]

def parse(ts):
    try:
        return dt.datetime.strptime(ts.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

# acute-HF admissions
ahf = set(l.strip() for l in open(f"{BASE}/_ahf_hadm.txt") if l.strip())

# first dialysis session per hadm, RESTRICTED to acute-HF admissions
first_dialysis, subj_of = {}, {}
with open(f"{BASE}/_dialysis_events.csv") as f:
    for subj, hadm, start, itemid in csv.reader(f):
        if hadm not in ahf:
            continue
        t = parse(start)
        if t is None:
            continue
        if hadm not in first_dialysis or t < first_dialysis[hadm]:
            first_dialysis[hadm] = t; subj_of[hadm] = subj

# lab times per (hadm, group) for anchored admissions
times = defaultdict(lambda: defaultdict(list))
with open(f"{BASE}/_labs4_times.csv") as f:
    for hadm, ct, g in csv.reader(f):
        if hadm in first_dialysis:
            t = parse(ct)
            if t is not None:
                times[hadm][g].append(t)

H = dt.timedelta(hours=1)
print(f"Acute-HF admissions with a dialysis session : {len(first_dialysis)}")
print(f"Distinct patients                           : {len(set(subj_of.values()))}")
print(f"\nWindow {PRE_H}h pre / {POST_H}h post\n")
print(f"{'lab':>6} | {'>=2 each  admits(pats)':>24} | {'>=3 each  admits(pats)':>24}")
print("-"*62)

meet3 = {g: set() for g in LABS}   # hadm sets meeting >=3 each, per lab
for g in LABS:
    r = {2:(0,set()), 3:(0,set())}
    for hadm, anchor in first_dialysis.items():
        tl = times[hadm].get(g, [])
        pre  = sum(1 for t in tl if anchor-PRE_H*H <= t < anchor)
        post = sum(1 for t in tl if anchor < t <= anchor+POST_H*H)
        for thr in (2,3):
            if pre >= thr and post >= thr:
                n,s = r[thr]; r[thr]=(n+1, s|{subj_of[hadm]})
        if pre >= 3 and post >= 3:
            meet3[g].add(hadm)
    print(f"{g:>6} | {r[2][0]:>10} ({len(r[2][1]):>4})       | {r[3][0]:>10} ({len(r[3][1]):>4})")

allfour = set.intersection(*[meet3[g] for g in LABS])
pats_all = {subj_of[h] for h in allfour}
print(f"\nAdmissions with >=3 pre & >=3 post for ALL FOUR labs: {len(allfour)} ({len(pats_all)} patients)")
