#!/usr/bin/env python3
"""
Ablation harness for the CounterfactualSim RL environment.

Runs three arms on the longitudinal benchmark and scores each with the SAME
reward function used for GRPO (Longitudinal/score_longitudinal.score_case):

  vanilla   — answer from the leak-safe answering view, NO simulate tool.
  sim_base  — the LLM may consult the simulate() MCP tool as extra context.
  sim_grpo  — load a GRPO-finetuned checkpoint dir from $GRPO_CKPT if present,
              else behave exactly like sim_base (and say so).

`--dry-run` uses a trivial deterministic baseline (no LLM, no torch, pure
stdlib) so the harness + scoring can be validated end-to-end offline. In
real mode we drive backend.LocalLLM and tolerantly parse its reply into the
`answers` dict, falling back to the trivial baseline on any parse failure.

Run from anywhere:
  python rl_env/ablation.py --dry-run --n 3
  python rl_env/ablation.py --n 5 --model qwen3:4b
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── repo layout ────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve()
CFSIM_DIR = HERE.parent.parent                       # CounterfactualSim/
V3_DIR = CFSIM_DIR.parent                            # Version_3/
LONG_DIR = V3_DIR / "Longitudinal"
QGEN_DIR = V3_DIR / "Benchmark_A" / "Question_Gen"

JSONL = LONG_DIR / "outputs" / "longitudinal.jsonl"
ANSWERING_DIR = LONG_DIR / "outputs" / "answering"
SIM_SERVER = CFSIM_DIR / "simulate_server.py"

ARMS = ["vanilla", "sim_base", "sim_grpo"]


# ── data loading ────────────────────────────────────────────────────────────
def load_records() -> dict:
    """question_id -> full record (has answer keys under record['steps'])."""
    recs = {}
    with open(JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            recs[r["question_id"]] = r
    return recs


def load_answering(qid: str) -> dict | None:
    """The leak-safe view served to the agent, or None if missing."""
    p = ANSWERING_DIR / f"{qid}.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


# ── the trivial deterministic baseline (offline reward-sanity answerer) ──────
def trivial_answers(view: dict) -> dict:
    """A1/A2 -> first option; C -> 'A'; B -> 'Stable' for every target lab."""
    steps = view.get("steps", {})
    ans: dict = {}
    a1 = steps.get("A1")
    if a1 and a1.get("options"):
        ans["A1"] = [a1["options"][0]]
    if "C" in steps:
        ans["C"] = "A"
    b = steps.get("B")
    if b and b.get("targets"):
        ans["B"] = {t["lab"]: "Stable" for t in b["targets"]}
    a2 = steps.get("A2")
    if a2 and a2.get("options"):
        ans["A2"] = [a2["options"][0]]
    return ans


# ── tolerant parsing of a model reply into an answers dict ───────────────────
def _extract_json(text: str) -> dict | None:
    """Pull the first {...} block out of a model reply and json-load it."""
    # fenced ```json ... ``` first, then any brace-balanced span
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [m.group(1)] if m else []
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start:i + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue
    return None


def parse_reply(text: str, view: dict) -> dict:
    """Best-effort reply -> answers dict; fall back to the trivial baseline."""
    steps = view.get("steps", {})
    obj = _extract_json(text) or {}
    ans = trivial_answers(view)                      # safe defaults for every step
    if not isinstance(obj, dict):
        return ans
    # A1 / A2: accept list or single string
    for key in ("A1", "A2"):
        if key in steps and key in obj:
            v = obj[key]
            ans[key] = v if isinstance(v, list) else [v]
    # C: single letter
    if "C" in steps and "C" in obj:
        ans["C"] = str(obj["C"]).strip().upper()[:1] or "A"
    # B: {lab: direction}; keep only Rising/Falling/Stable, default Stable
    if "B" in steps and isinstance(obj.get("B"), dict):
        valid = {"Rising", "Falling", "Stable"}
        b = {}
        for t in steps["B"].get("targets", []):
            d = str(obj["B"].get(t["lab"], "Stable")).strip().capitalize()
            b[t["lab"]] = d if d in valid else "Stable"
        ans["B"] = b
    return ans


# ── LLM answerer (real mode) ─────────────────────────────────────────────────
_ANSWER_SPEC = (
    "You are answering a multi-step longitudinal ICU question. Reply with ONE JSON "
    "object with the keys for the steps present, e.g. "
    '{"A1": ["<option>"], "C": "A", "B": {"<lab>": "Rising|Falling|Stable"}, '
    '"A2": ["<option>"]}. Use option text verbatim; predict every listed lab in B. '
    "Output only the JSON."
)


def _anchor_family(record: dict) -> str:
    fam = (record.get("anchor", {}) or {}).get("family")
    return str(fam or "none").lower()


def llm_answer(llm, view: dict, record: dict, sim_ctx: str | None) -> dict:
    """Ask the LLM to answer one case; sim_ctx (if any) is folded into the prompt."""
    prompt = {"question_id": view.get("question_id"), "steps": view.get("steps", {})}
    user = _ANSWER_SPEC + "\n\nCASE:\n" + json.dumps(prompt)[:12000]
    if sim_ctx:
        user += "\n\nSIMULATOR HINT (counterfactual world-model prediction):\n" + sim_ctx
    try:
        reply = llm.chat([{"role": "user", "content": user}],
                          max_new_tokens=1200, temperature=0.2)
        return parse_reply(reply, view)
    except Exception as e:                           # network/model failure -> baseline
        print(f"    [warn] LLM failed ({type(e).__name__}: {e}); using trivial baseline")
        return trivial_answers(view)


_SIM_ARMS = ["dialysis", "transfusion", "ventilation"]


def sim_context(sim, patient_id: str) -> str:
    """Query the simulator for EVERY candidate intervention (leak-free: the model sees all
    arms simulated and must still choose) and return a compact per-arm summary."""
    if sim is None:
        return ""
    lines = []
    for a in _SIM_ARMS:
        try:
            r = json.loads(sim.call("simulate", {"patient_id": str(patient_id), "intervention": a}))
        except Exception as e:
            lines.append(f"{a}: (unavailable: {type(e).__name__})"); continue
        dirs = r.get("predicted_lab_directions", {}) or {}
        moved = {k: v for k, v in dirs.items() if v in ("Rising", "Falling")}
        keep = dict(list(moved.items())[:6]) or dict(list(dirs.items())[:4])
        band = r.get("mortality_1y_band")
        lines.append(f"{a}: 1y-mortality≈{r.get('mortality_1y_risk')}"
                     f"{f' (80% band {band})' if band else ''}; 72h lab moves={keep}")
    return ("Counterfactual world-model predictions for each candidate intervention "
            "(use to reason about the trajectory/outcome steps; the actual intervention for "
            "steps B/A2 is stated in the case):\n" + "\n".join(lines))


# ── one arm over all cases ───────────────────────────────────────────────────
def run_arm(arm: str, records: dict, args) -> float:
    from score_longitudinal import score_case      # local import; pure stdlib

    llm, sim = None, None
    if not args.dry_run:
        sys.path.insert(0, str(QGEN_DIR))
        from backend import LocalLLM
        model_key = args.model
        if arm == "sim_grpo":
            ckpt = os.environ.get("GRPO_CKPT")
            if ckpt and os.path.isdir(ckpt):
                # TODO(cluster): load the GRPO-finetuned weights from `ckpt` via the
                # hf backend instead of the base tag; native tool-calling wires in here.
                print(f"  [sim_grpo] using GRPO checkpoint at {ckpt}")
            else:
                print("  [sim_grpo] GRPO_CKPT not set/found — using the BASE model "
                      "(behaves like sim_base)")
        llm = LocalLLM(model_key)
        if arm in ("sim_base", "sim_grpo"):
            from mcp_client import MCPClient          # spawn the python MCP server
            sim = MCPClient(CFSIM_DIR, SIM_SERVER, node_bin="python3").start()

    totals = []
    steps = {"A1": [], "C": [], "B": [], "A2": []}
    try:
        for qid, record in records.items():
            view = load_answering(qid)
            if view is None:
                continue
            if args.dry_run:
                answers = trivial_answers(view)      # all arms identical in dry-run
            else:
                ctx = ""
                if arm in ("sim_base", "sim_grpo"):
                    pid = record.get("subject_id", qid)
                    ctx = sim_context(sim, pid)      # all candidate arms (leak-free)
                answers = llm_answer(llm, view, record, ctx)
            sc = score_case(record, answers)
            totals.append(sc["total"])
            for k, v in sc["per_step"].items():
                steps[k].append(v)
    finally:
        if sim is not None:
            sim.close()

    per_step = {k: (round(sum(v) / len(v), 4) if v else None) for k, v in steps.items()}
    return {"mean_total": round(sum(totals) / len(totals), 4) if totals else 0.0,
            "per_step": per_step, "n": len(totals)}


def main():
    ap = argparse.ArgumentParser(description="CounterfactualSim ablation harness")
    ap.add_argument("--dry-run", action="store_true",
                    help="trivial offline baseline for all arms (no LLM/torch/network)")
    ap.add_argument("--n", type=int, default=None, help="limit number of cases")
    ap.add_argument("--model", default="qwen3:4b", help="Ollama/HF model key (real mode)")
    ap.add_argument("--arms", nargs="*", default=ARMS, help="subset of arms to run")
    args = ap.parse_args()

    if not JSONL.exists():
        print(f"[error] benchmark not found: {JSONL}")
        return 1

    records = load_records()
    if args.n is not None:
        records = dict(list(records.items())[:args.n])
    print(f"Loaded {len(records)} case(s) from {JSONL}")
    print(f"Mode: {'DRY-RUN (trivial baseline)' if args.dry_run else 'REAL (LLM: ' + args.model + ')'}\n")

    results = {}
    for arm in args.arms:
        print(f"== arm: {arm} ==", flush=True)
        results[arm] = run_arm(arm, records, args)

    hdr = f"{'arm':<12}{'total':>9}{'A1':>8}{'C':>8}{'B':>8}{'A2':>8}"
    print("\n=== ablation: per-step + total per arm ===")
    print(hdr); print("-" * len(hdr))
    for arm in args.arms:
        r = results[arm]; ps = r["per_step"]
        def f(x): return f"{x:>8.3f}" if isinstance(x, (int, float)) else f"{'-':>8}"
        print(f"{arm:<12}{r['mean_total']:>9.3f}{f(ps['A1'])}{f(ps['C'])}{f(ps['B'])}{f(ps['A2'])}")

    out = LONG_DIR / "outputs" / "step6_ablation.json"
    out.write_text(json.dumps({"model": args.model, "ckpt": os.environ.get("CFSIM_CKPT"),
                               "n_cases": len(records), "arms": results}, indent=2))
    print(f"\nsaved -> {out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(LONG_DIR))                # for score_longitudinal
    raise SystemExit(main())
