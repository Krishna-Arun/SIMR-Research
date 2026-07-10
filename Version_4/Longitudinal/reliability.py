#!/usr/bin/env python3
"""
Scoring reliability for the v4 agent-judged benchmark.

The user asked for Cronbach's alpha + inter-rater reliability. This module treats each JUDGE
CONFIGURATION (a judge run at a given seed/temperature, or a different judge model) as a
"rater" and measures agreement on the per-case scores.

  - cronbach_alpha(M)  : internal consistency of raters, M = [n_items, n_raters] of scalar scores
                         (here: per-case `total` from each judge). alpha >= 0.7 ~ acceptable.
  - cohen_kappa(a, b)  : chance-corrected agreement between two raters on a CATEGORICAL score
                         (here: `fully_solved` 0/1, or a 3-level {0,0.5,1} judgement).

Two ways to feed it:
  A) one scored file that used --judge-runs K  -> uses each result's `judge_totals` list.
  B) several scored files from DIFFERENT judge models -> pass them all as positional args.

Usage:
  python reliability.py outputs_v4/answers_gemma.scored.gpt-oss-20b.json            # (A) judge-runs
  python reliability.py A.scored.gpt-oss-20b.json A.scored.qwen3-8b.json             # (B) two models
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from statistics import mean, variance


def cronbach_alpha(matrix):
    """matrix: list of rows (items), each a list of rater scores. Returns alpha in (-inf, 1]."""
    n_raters = len(matrix[0])
    if n_raters < 2 or len(matrix) < 2:
        return None
    # per-rater variance (down columns), and variance of item totals (across rows)
    cols = [[row[j] for row in matrix] for j in range(n_raters)]
    item_totals = [sum(row) for row in matrix]
    var_items = variance(item_totals)
    if var_items == 0:
        return None
    sum_var_cols = sum(variance(c) for c in cols)
    return (n_raters / (n_raters - 1)) * (1 - sum_var_cols / var_items)


def cohen_kappa(a, b):
    """a, b: equal-length lists of categorical labels. Returns kappa."""
    n = len(a)
    if n == 0:
        return None
    cats = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe != 1 else 1.0


def _load(path):
    d = json.load(open(path))
    return {r["question_id"]: r for r in d["results"]}


def main(argv):
    if not argv:
        print(__doc__); return 1
    files = argv

    if len(files) == 1:
        # (A) multiple judge runs inside one file
        res = _load(files[0])
        rows = [r["judge_totals"] for r in res.values()
                if isinstance(r.get("judge_totals"), list) and len(r["judge_totals"]) >= 2]
        if not rows:
            print("[reliability] single file but no multi-run judge_totals (use --judge-runs>=2 "
                  "in score_chain, or pass multiple scored files).")
            return 1
        k = min(len(r) for r in rows)
        M = [r[:k] for r in rows]
        alpha = cronbach_alpha(M)
        # kappa between run 0 and run 1 on 3-level bucketed totals
        buck = lambda x: 0 if x < 0.34 else (1 if x < 0.67 else 2)
        a0 = [buck(r[0]) for r in M]; a1 = [buck(r[1]) for r in M]
        print(f"[reliability] {len(M)} items x {k} judge runs (file: {files[0]})")
        print(f"  Cronbach's alpha (across judge runs): {alpha:.3f}" if alpha is not None else
              "  Cronbach's alpha: undefined")
        print(f"  Cohen's kappa (run0 vs run1, 3-level): {cohen_kappa(a0, a1):.3f}")
        return 0

    # (B) several judge MODELS -> align on shared question_ids
    loaded = [_load(f) for f in files]
    common = set(loaded[0])
    for d in loaded[1:]:
        common &= set(d)
    common = sorted(common)
    if len(common) < 2:
        print("[reliability] <2 shared question_ids across files."); return 1
    M = [[d[q]["total"] for d in loaded] for q in common]
    alpha = cronbach_alpha(M)
    print(f"[reliability] {len(common)} shared items x {len(files)} judge models")
    for f in files:
        print(f"    - {f}")
    print(f"  Cronbach's alpha (across judge models): {alpha:.3f}" if alpha is not None else
          "  Cronbach's alpha: undefined")
    buck = lambda x: 0 if x < 0.34 else (1 if x < 0.67 else 2)
    for i, j in combinations(range(len(files)), 2):
        a = [buck(d) for d in [loaded[i][q]["total"] for q in common]]
        b = [buck(d) for d in [loaded[j][q]["total"] for q in common]]
        print(f"  Cohen's kappa (model{i} vs model{j}, 3-level): {cohen_kappa(a, b):.3f}")
    # binary fully_solved agreement
    for i, j in combinations(range(len(files)), 2):
        a = [int(bool(loaded[i][q].get("fully_solved"))) for q in common]
        b = [int(bool(loaded[j][q].get("fully_solved"))) for q in common]
        print(f"  Cohen's kappa (model{i} vs model{j}, fully_solved): {cohen_kappa(a, b):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
