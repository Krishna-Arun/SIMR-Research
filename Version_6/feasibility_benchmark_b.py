#!/usr/bin/env python3
"""Feasibility of Benchmark B v1: dialysis -> creatinine trajectory.
For each admission's FIRST dialysis session, count serum-creatinine (50912)
measurements in the pre/post windows and report how many admissions clear
various window / threshold combinations."""
import csv, datetime as dt
from collections import defaultdict

BASE = "/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/Version_6"

def parse(ts):
    try:
        return dt.datetime.strptime(ts.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

# first dialysis session per hadm_id
first_dialysis = {}          # hadm_id -> anchor datetime
subj_of = {}                 # hadm_id -> subject_id
with open(f"{BASE}/_dialysis_events.csv") as f:
    for subj, hadm, start, itemid in csv.reader(f):
        t = parse(start)
        if t is None or not hadm:
            continue
        if hadm not in first_dialysis or t < first_dialysis[hadm]:
            first_dialysis[hadm] = t
            subj_of[hadm] = subj

# creatinine times per hadm (only for anchored admissions)
creat = defaultdict(list)
with open(f"{BASE}/_creat_times.csv") as f:
    for hadm, ct in csv.reader(f):
        if hadm in first_dialysis:
            t = parse(ct)
            if t is not None:
                creat[hadm].append(t)

H = dt.timedelta(hours=1)
combos = [(48,72),(72,72),(24,48),(48,48),(72,120)]
thresholds = [2,3]

print(f"Admissions with a dialysis session : {len(first_dialysis)}")
print(f"Distinct patients                  : {len(set(subj_of.values()))}")
print()
print(f"{'pre/post(h)':>12} | {'>=2 each':>10} {'pats':>6} | {'>=3 each':>10} {'pats':>6}")
print("-"*56)
for pre_h, post_h in combos:
    row = {2:(0,set()), 3:(0,set())}
    for hadm, anchor in first_dialysis.items():
        pre = sum(1 for t in creat.get(hadm,[]) if anchor-pre_h*H <= t < anchor)
        post = sum(1 for t in creat.get(hadm,[]) if anchor < t <= anchor+post_h*H)
        for thr in thresholds:
            if pre >= thr and post >= thr:
                n,s = row[thr]; row[thr] = (n+1, s|{subj_of[hadm]})
    print(f"{pre_h:>4}/{post_h:<7} | {row[2][0]:>10} {len(row[2][1]):>6} | {row[3][0]:>10} {len(row[3][1]):>6}")
