"""Benchmark B ground-truth trajectory labels — deterministic, data-derived (the LLM does NOT invent them).

For each core lab around a procedure (time-zero = procedure start), within post_window_h:
  baseline  = last pre-procedure value
  post_rep  = last post-procedure value (representative of where it ended up)
  ref range = median ref_range_lower/upper from the lab's own rows (per-row in labevents, like "abnormal")

Direction (user spec — "Stable = within the accepted range"):
  Stable  if ref_lower <= post_rep <= ref_upper
  Rising  if post_rep >  ref_upper
  Falling if post_rep <  ref_lower
Fallback when no reference range is recorded: relative change vs baseline (|Δ| < 15% = Stable).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STABLE_REL = 0.15   # fallback threshold when ref range is missing


def _direction(post_rep: float, baseline: float, lo, hi) -> tuple[str, str]:
    """Return (direction, basis).

    Stable = the lab ends WITHIN its reference range (stays normal). If it ends OUT of range, the
    direction is the SIGN OF MOVEMENT vs baseline (up=Rising, down=Falling) — so a creatinine that
    falls 1.7->1.4 but is still above range is Falling, not Rising.
    """
    have_range = lo is not None and hi is not None and not (pd.isna(lo) or pd.isna(hi)) and hi > lo
    if have_range and lo <= post_rep <= hi:
        return "Stable", "within_range"
    if have_range:                                    # out of range -> direction of movement
        return ("Rising" if post_rep >= baseline else "Falling"), "out_of_range"
    # no reference range: fall back to relative change vs baseline
    rel = (post_rep - baseline) / (abs(baseline) + 1e-6)
    if abs(rel) < STABLE_REL:
        return "Stable", "rel_change"
    return ("Rising" if rel > 0 else "Falling"), "rel_change"


def trajectories_for_procedure(hadm_labs: pd.DataFrame, starttime, window_h: float,
                               min_pre: int, min_post: int) -> dict:
    """hadm_labs: core-lab rows for ONE admission. Returns {label: {...ground truth...}} for
    trajectory-able core labs only."""
    out: dict = {}
    if hadm_labs is None or len(hadm_labs) == 0:
        return out
    dt = (hadm_labs["charttime"] - starttime).dt.total_seconds() / 3600.0
    df = hadm_labs.assign(_dt=dt)
    for label, g in df.groupby("label"):
        g = g.sort_values("charttime")
        pre = g[g["_dt"] <= 0]
        post = g[(g["_dt"] > 0) & (g["_dt"] <= window_h)]
        if len(pre) < min_pre or len(post) < min_post:
            continue
        baseline = float(pre["valuenum"].iloc[-1])
        post_rep = float(post["valuenum"].iloc[-1])
        lo = float(np.nanmedian(g["ref_range_lower"])) if g["ref_range_lower"].notna().any() else None
        hi = float(np.nanmedian(g["ref_range_upper"])) if g["ref_range_upper"].notna().any() else None
        direction, basis = _direction(post_rep, baseline, lo, hi)
        unit = str(g["valueuom"].dropna().iloc[-1]) if g["valueuom"].notna().any() else ""
        out[str(label)] = {
            "direction": direction, "basis": basis,
            "baseline": round(baseline, 3), "post_rep": round(post_rep, 3),
            "ref_lower": round(lo, 3) if lo is not None else None,
            "ref_upper": round(hi, 3) if hi is not None else None,
            "unit": unit, "n_pre": int(len(pre)), "n_post": int(len(post)),
            "pre_series": [{"value": round(float(v), 3), "h": round(float(t), 1)}
                           for v, t in zip(pre["valuenum"], pre["_dt"]) if pd.notna(v)],
            "post_series": [{"value": round(float(v), 3), "h": round(float(t), 1)}
                            for v, t in zip(post["valuenum"], post["_dt"]) if pd.notna(v)],
        }
    return out
