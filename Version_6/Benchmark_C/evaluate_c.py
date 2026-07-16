#!/usr/bin/env python3
"""
Benchmark C evaluation harness (matched-pair intervention discrimination).

Each item: two matched patients' pre-intervention states (P1, P2, unlabeled),
the two candidate interventions, and ONE observed 72h post-state. The agent
predicts which intervention produced that post-state: dialysis | diuresis.
Chance = 50% (labels are exactly 50/50).

Usage:
  python3 evaluate_c.py --backend local --limit 3 --effort low
  python3 evaluate_c.py --backend local --effort low        # full 424
  python3 evaluate_c.py --backend anthropic                 # needs API creds
"""
import argparse, json, os, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "benchmark_b"))  # evaluate.py lives in benchmark_b/
from evaluate import load_local, _extract_json, _final_channel  # reuse local-backend helpers

CLASSES = ["dialysis", "diuresis"]

SYSTEM = (
    "You are a critical-care nephrology reasoning agent. Two acute-HF patients with "
    "near-identical baseline states each received a DIFFERENT intervention. Given both "
    "baselines, the two candidate interventions, and one observed 72-hour post-intervention "
    "trajectory of core metabolic labs, you determine which intervention produced it by "
    "reasoning about each treatment's causal effect on the labs."
)

TASK = """\
Exactly one of the two interventions above produced the OBSERVED POST-STATE below.
Decide which one, by comparing the observed 72h lab trajectory against the causal
signature of each intervention (relative to the matched baselines). Consider all four
labs together — no single lab is decisive.
Answer with exactly one word: dialysis  OR  diuresis.
"""


def _series(pts):
    if not pts:
        return "      (none)"
    out = []
    for p in pts:
        lo, hi = p.get("ref_low"), p.get("ref_high")
        rng = f"[{lo}-{hi}]" if lo is not None and hi is not None else "[ref n/a]"
        out.append(f"      t={p['h']:+.1f}h  {p['v']}  ref{rng}")
    return "\n".join(out)


def render_state(st, label):
    L = [f"--- {label} (pre-intervention baseline) ---"]
    d = st.get("demographics", {})
    L.append(f"  {d.get('gender','?')}, age {d.get('age','?')}")
    comorbid = [k for k, v in st.get("comorbidities", {}).items() if v]
    L.append("  comorbidities: " + (", ".join(comorbid) if comorbid else "none coded"))
    cc = st.get("coronary_contrast", {})
    L.append("  coronary/contrast: " + ("yes" if cc.get("present") else "none"))
    meds = st.get("medications_pre_window", {})
    if meds:
        L.append("  pre-intervention meds (by class, with dose):")
        for cls, entries in sorted(meds.items()):
            items = []
            for e in entries:
                dose = f" {e['dose_val']}{(' '+e['dose_unit']) if e.get('dose_unit') else ''}" if e.get("dose_val") else ""
                rt = f" {e['route']}" if e.get("route") else ""
                items.append(f"{e['drug']}{dose}{rt}".strip())
            L.append(f"    - {cls}: " + "; ".join(items))
    ctx = st.get("context_labs_baseline", {})
    if ctx:
        L.append("  baseline context labs:")
        for name, v in sorted(ctx.items()):
            lo, hi = v.get("ref_low"), v.get("ref_high")
            rng = f"[{lo}-{hi}]" if lo is not None and hi is not None else "[ref n/a]"
            L.append(f"    - {name}: {v['value']} ref{rng} ({v.get('status')})")
    L.append("  pre-intervention core-lab trajectories:")
    for lab, pts in st["pre_window_target_labs"].items():
        L.append(f"    {lab}:")
        L.append(_series(pts))
    return "\n".join(L)


def build_prompt(item):
    iv = item["interventions"]
    L = ["TWO CANDIDATE INTERVENTIONS:",
         f"  - dialysis: {iv['dialysis']}",
         f"  - diuresis: {iv['diuresis']}",
         "",
         "TWO MATCHED PATIENTS (one received dialysis, one received diuresis — you are NOT told which):",
         render_state(item["patients"]["P1"], "Patient 1"),
         render_state(item["patients"]["P2"], "Patient 2"),
         "",
         "OBSERVED POST-STATE (72h post-intervention core-lab trajectories, from ONE of the two patients):"]
    for lab, pts in item["observed_post_state"].items():
        L.append(f"  {lab}:")
        L.append(_series(pts))
    return "\n".join(L) + "\n\n" + TASK


SCHEMA = {"type": "object",
          "properties": {"intervention": {"type": "string", "enum": CLASSES}},
          "required": ["intervention"], "additionalProperties": False}
JSON_INSTR = ('\nRespond with ONLY this JSON object (no prose):\n'
              '{"intervention": "<dialysis|diuresis>"}\n')


def predict_local(model, tok, dev, item, effort):
    import torch
    reasoning = effort if effort in ("low", "medium", "high") else "low"
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": build_prompt(item) + JSON_INSTR}]
    kw = dict(add_generation_prompt=True, return_tensors="pt", return_dict=True)
    try:
        enc = tok.apply_chat_template(messages, reasoning_effort=reasoning, **kw)
    except TypeError:
        enc = tok.apply_chat_template(messages, **kw)
    enc = {k: v.to(dev) for k, v in enc.items()}
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=1536, do_sample=False, pad_token_id=tok.eos_token_id)
    raw = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=False)
    obj = _extract_json(_final_channel(raw))
    lbl = obj.get("intervention")
    if lbl not in CLASSES:
        raise ValueError(f"bad label: {lbl!r}")
    return lbl


def predict_anthropic(client, item, model, effort):
    resp = client.messages.create(
        model=model, max_tokens=3000, thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}, "effort": effort},
        system=SYSTEM, messages=[{"role": "user", "content": build_prompt(item)}])
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))["intervention"]


def macro_f1(pairs):
    f1s = []
    for c in CLASSES:
        tp = sum(1 for t, p in pairs if t == c and p == c)
        fp = sum(1 for t, p in pairs if t != c and p == c)
        fn = sum(1 for t, p in pairs if t == c and p != c)
        pr = tp/(tp+fp) if tp+fp else 0.0
        rc = tp/(tp+fn) if tp+fn else 0.0
        f1s.append(2*pr*rc/(pr+rc) if pr+rc else 0.0)
    return sum(f1s)/len(f1s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(HERE, "cases_c.jsonl"))
    ap.add_argument("--backend", default="local", choices=["local", "anthropic"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(HERE, "results_c.jsonl"))
    args = ap.parse_args()
    if args.model is None:
        args.model = "openai/gpt-oss-20b" if args.backend == "local" else "claude-opus-4-8"

    items = [json.loads(l) for l in open(args.cases)]
    if args.limit:
        items = items[:args.limit]
    print(f"Loaded {len(items)} items")

    results = {}; errors = 0
    if args.backend == "local":
        import time
        # crash-safe: append each finished item to a .partial sidecar; resume skips them.
        partial = args.out + ".partial"
        if os.path.exists(partial):
            for l in open(partial):
                try: row = json.loads(l)
                except Exception: continue
                results[row["item_id"]] = row["pred"]
            print(f"  resume: loaded {len(results)} completed items from {os.path.basename(partial)}")
        todo = [it for it in items if it["item_id"] not in results]
        print(f"  {len(todo)} items to run ({len(results)} already done)")
        model, tok, dev = load_local(args.model)
        pf = open(partial, "a")
        t0 = time.monotonic()
        for i, it in enumerate(todo, 1):
            try:
                pred = predict_local(model, tok, dev, it, args.effort)
                results[it["item_id"]] = pred
                pf.write(json.dumps({"item_id": it["item_id"], "pred": pred,
                                     "truth": it["answer"], "correct": pred == it["answer"]})+"\n")
                pf.flush()
            except Exception as e:
                errors += 1; print(f"  ! {it['item_id']}: {e}", file=sys.stderr)
            r = (time.monotonic()-t0)/i
            print(f"  {i}/{len(todo)} ({errors} err) {r:.1f}s/it eta {r*(len(todo)-i)/60:.0f}min", flush=True)
        pf.close()
    else:
        import anthropic
        client = anthropic.Anthropic()
        def work(it): return it["item_id"], predict_anthropic(client, it, args.model, args.effort)
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(work, it): it for it in items}
            for fut in as_completed(futs):
                try:
                    iid, pred = fut.result(); results[iid] = pred
                except Exception as e:
                    errors += 1; print(f"  ! {futs[fut]['item_id']}: {e}", file=sys.stderr)
                done += 1
                if done % 20 == 0 or done == len(items):
                    print(f"  {done}/{len(items)} ({errors} err)")

    truth = {it["item_id"]: it["answer"] for it in items}
    with open(args.out, "w") as fo:
        for it in items:
            iid = it["item_id"]
            if iid in results:
                fo.write(json.dumps({"item_id": iid, "pred": results[iid],
                                     "truth": truth[iid], "correct": results[iid] == truth[iid]})+"\n")

    pairs = [(truth[i], results[i]) for i in results]
    print("\n===================== RESULTS =====================")
    print(f"backend={args.backend} model={args.model} effort={args.effort}  scored={len(pairs)}")
    if pairs:
        acc = sum(1 for t, p in pairs if t == p)/len(pairs)
        print(f"accuracy = {acc:.3f}   (chance = 0.500)   macro-F1 = {macro_f1(pairs):.3f}")
        for c in CLASSES:
            sub = [(t, p) for t, p in pairs if t == c]
            a = sum(1 for t, p in sub if t == p)/len(sub) if sub else 0
            print(f"  true={c:9} n={len(sub):3}  recall={a:.3f}")
        print(f"prediction distribution: {dict(Counter(p for _, p in pairs))}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
