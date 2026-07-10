"""serialize_rollout.py — Route A: render a rollout dict (from rollout_api) into a compact text
SIMULATOR-EVIDENCE block for in-prompt injection into a frozen or fine-tuned LLM.

Design goals: ~350-500 tokens, deterministic, carries (a) baseline state + reliability flag,
(b) per-candidate final mortality-risk band + key lab directions, (c) treatment-contrast deltas,
(d) an explicit calibration caveat that transfers the model's known reliability profile into the prompt.
The block is APPENDED to the byte-identical vanilla prompt (fairness invariant, see plan §Route A).
"""
from __future__ import annotations

from typing import Optional

# human-readable labels for the deterministic plan keys emitted by enumerate_candidate_plans
_PLAN_LABELS = {
    "factual": "FACTUAL (treatment actually given)",
    "no_treatment": "NO TREATMENT",
    "alt_arm_pci": "ALTERNATIVE: perform PCI",
    "alt_arm_medical": "ALTERNATIVE: withhold revascularization (medical only)",
}


def _plan_label(key: str) -> str:
    if key in _PLAN_LABELS:
        return _PLAN_LABELS[key]
    if key.startswith("remove_"):
        return f"WITHHOLD {key[len('remove_'):]}"
    if key.startswith("add_"):
        return f"ADD {key[len('add_'):]}"
    return key


def _direction(traj: list, lab: str) -> Optional[str]:
    """First-step vs last-step mean → ↑ / ↓ / → (None if lab not tracked)."""
    if not traj or lab not in traj[0]:
        return None
    first = traj[0][lab]["mean"]
    last = traj[-1][lab]["mean"]
    d = last - first
    if abs(d) <= 0.05 * abs(first) + 1e-6:
        return f"{lab} → ({last:g})"
    arrow = "↑" if d > 0 else "↓"
    return f"{lab} {arrow} {first:g}→{last:g}"


def _pick_labs(rollout: dict, n: int = 3) -> list:
    """Prefer abnormal-baseline labs (where the sim is reliable), then fill from labs_show."""
    abn = rollout.get("reliability", {}).get("abnormal_baseline_labs", [])
    show = rollout.get("labs_show", [])
    ordered = list(dict.fromkeys(list(abn) + list(show)))
    return ordered[:n]


def serialize(rollout: dict, style: str = "structured") -> str:
    labs = _pick_labs(rollout, n=3)
    H = rollout.get("horizon_steps")
    total_h = sum(rollout.get("delta_t_hours", []) or [])

    lines = []
    lines.append("SIMULATOR EVIDENCE — CLMBR-JEPA counterfactual world model "
                 "(MC K=64; 10–90% bands; deconfounded via IPW + CRN adversary)")
    base = rollout.get("baseline_labs", {})
    if base:
        lines.append("Baseline state: " + ", ".join(f"{k} {v:g}" for k, v in base.items()))
    lines.append("Reliability: " + rollout.get("reliability", {}).get("flag", "unknown"))
    lines.append("")
    lines.append(f"Forecasts over next {H} steps (~{total_h:g}h) — final mortality risk "
                 "[10–90%] and key lab directions:")

    for key, p in rollout["plans"].items():
        fm = p["final_mortality_risk"]
        dirs = [d for d in (_direction(p["lab_trajectory"], lab) for lab in labs) if d]
        dirtxt = ("  |  " + ", ".join(dirs)) if dirs else ""
        lines.append(f"• {_plan_label(key):<42} mortality {fm['mean']:.2f} "
                     f"[{fm['lo']:.2f}–{fm['hi']:.2f}]{dirtxt}")

    tc = rollout.get("treatment_contrast", {})
    if tc.get("deltas"):
        base_lbl = _plan_label(tc.get("baseline_plan", ""))
        parts = [f"{_plan_label(k)} {'+' if v >= 0 else ''}{v:g}" for k, v in tc["deltas"].items()]
        lines.append("")
        lines.append(f"Treatment contrast (Δ final mortality risk vs {base_lbl}): " + "; ".join(parts))

    lines.append("")
    lines.append("CAVEAT: magnitudes are indicative, not exact; trust the DIRECTION of effect, and weight "
                 "it most on abnormal-baseline (RELIABLE) cases. Uncertainty bands widen over the horizon.")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).resolve().parent / "tests/_out/smoke_rollout.json"
    print(serialize(json.loads(p.read_text())))
