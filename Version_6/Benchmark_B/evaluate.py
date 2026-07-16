#!/usr/bin/env python3
"""
Benchmark B v1 - evaluation harness
===================================
Feeds each case's PRE-procedure state to an agent (Claude) and asks it to
predict, for all four BMP labs, the reference-range MEMBERSHIP change over the
72h post-dialysis window (moved_into_range / stayed / moved_out_of_range), with
a causal justification. Scores predictions against the ground-truth labels.

The agent never sees the post-window measurements or the labels — only `state`.

Usage:
  python3 evaluate.py --dry-run                 # no API; majority-class stub (plumbing + baseline)
  python3 evaluate.py --limit 5                 # 5 cases, live
  python3 evaluate.py                            # full eligible set, live
  python3 evaluate.py --model claude-opus-4-8 --effort medium --workers 6

Auth: uses the standard Anthropic credential chain (ANTHROPIC_API_KEY or an
`ant auth login` profile). If neither is set, run `ant auth status`.
"""
import argparse, json, os, sys
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = ["moved_into_range", "stayed", "moved_out_of_range"]
# schema field name -> human clinical name (as stored in the case targets)
LAB_FIELDS = {
    "creatinine": "Creatinine",
    "bun": "BUN (Urea Nitrogen)",
    "potassium": "Potassium",
    "bicarbonate": "Bicarbonate",
}

# ----------------------------------------------------------------------
# Prompt construction (state only)
# ----------------------------------------------------------------------
SYSTEM = (
    "You are a critical-care nephrology reasoning agent. Given a patient's "
    "clinical state immediately BEFORE an intervention during an acute heart "
    "failure admission, you predict how core metabolic labs will respond over "
    "the 72 hours AFTER the intervention, reasoning from the intervention's "
    "physiological/pharmacological causal effects."
)

TASK = """\
For each of the four labs below, predict how its REFERENCE-RANGE MEMBERSHIP will
change from BASELINE (the last pre-intervention measurement shown) to the LAST
measurement taken within 72 hours after the intervention starts. Choose exactly one:

- moved_into_range   : baseline is OUT of its reference range (High or Low) and
                       the last post value is WITHIN range  (normalization)
- moved_out_of_range : baseline is WITHIN range and the last post value is OUT
                       of range  (deterioration)
- stayed             : in-range membership is unchanged (Within->Within, or
                       Out->Out, including a High<->Low flip that stays out)

Base your prediction on the intervention, the pre-intervention lab trajectory,
active medications, comorbidities, and context labs, reasoning about the
mechanism (dialytic clearance, diuretic effect, acid-base shift, etc.).
Reason only from the state provided.
"""


def fmt_series(points):
    if not points:
        return "    (none)"
    out = []
    for p in points:
        lo, hi = p.get("ref_low"), p.get("ref_high")
        rng = f"[{lo}-{hi}]" if lo is not None and hi is not None else "[ref n/a]"
        out.append(f"    t={p['h']:+.1f}h  value={p['v']}  ref{rng}")
    return "\n".join(out)


def build_prompt(case):
    s = case["state"]
    demo = s.get("demographics", {})
    adm = s.get("admission", {})
    lines = []
    lines.append(f"PATIENT: {demo.get('gender','?')}, age {demo.get('age','?')}; "
                 f"admission type {adm.get('admission_type','?')}.")
    if case.get("anchor_description"):
        lines.append(f"INTERVENTION (anchor): {case['anchor_description']}")
    else:
        d = case.get("dialysis", {})
        lines.append(f"INTERVENTION (anchor): {d.get('modality','?')} dialysis, "
                     f"duration {d.get('duration_hours','?')} h.")
    comorbid = [k for k, v in s.get("comorbidities", {}).items() if v]
    lines.append("COMORBIDITIES: " + (", ".join(comorbid) if comorbid else "none coded"))
    cc = s.get("coronary_contrast", {})
    if cc.get("present"):
        offs = ", ".join(f"{p['icd']}({p['offset_days']:+d}d)" for p in cc.get("procedures", []))
        lines.append(f"CORONARY/CONTRAST PROCEDURE(S): {offs}")
    else:
        lines.append("CORONARY/CONTRAST PROCEDURE(S): none this admission")

    meds = s.get("medications_pre_window", {})
    if meds:
        lines.append("PRE-INTERVENTION ACTIVE MEDICATIONS (by class, with dose):")
        for cls, entries in sorted(meds.items()):
            items = []
            for e in entries:
                dose = ""
                if e.get("dose_val"):
                    dose = f" {e['dose_val']}{(' ' + e['dose_unit']) if e.get('dose_unit') else ''}"
                per = f" x{e['doses_per_24h']}/day" if e.get("doses_per_24h") else ""
                rt = f" {e['route']}" if e.get("route") else ""
                items.append(f"{e['drug']}{dose}{per}{rt}".strip())
            lines.append(f"  - {cls}: " + "; ".join(items))
    else:
        lines.append("PRE-INTERVENTION ACTIVE MEDICATIONS: none detected")

    ctx = s.get("context_labs_baseline", {})
    if ctx:
        lines.append("BASELINE CONTEXT LABS:")
        for name, v in sorted(ctx.items()):
            lo, hi = v.get("ref_low"), v.get("ref_high")
            rng = f"[{lo}-{hi}]" if lo is not None and hi is not None else "[ref n/a]"
            lines.append(f"  - {name}: {v['value']} ref{rng} ({v.get('status')}) "
                         f"{v.get('hours_before')}h before")

    lines.append("\nPRE-INTERVENTION TARGET-LAB TRAJECTORIES (t relative to the intervention):")
    for field, cname in LAB_FIELDS.items():
        lines.append(f"  {cname}:")
        lines.append(fmt_series(s["pre_window_target_labs"][cname]))

    return "\n".join(lines) + "\n\n" + TASK


# ----------------------------------------------------------------------
# Structured-output schema (forces validated per-lab label + rationale)
# ----------------------------------------------------------------------
def lab_obj():
    return {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": LABELS},
        },
        "required": ["label"],
        "additionalProperties": False,
    }

SCHEMA = {
    "type": "object",
    "properties": {f: lab_obj() for f in LAB_FIELDS},
    "required": list(LAB_FIELDS),
    "additionalProperties": False,
}


# ----------------------------------------------------------------------
# Model call
# ----------------------------------------------------------------------
def predict_live(client, case, model, effort):
    resp = client.messages.create(
        model=model,
        max_tokens=3000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": SCHEMA},
                       "effort": effort},
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(case)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {getattr(resp,'stop_details',None)}")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def predict_dry(case):
    # majority-class stub: predict the modal label of each lab (established below)
    return {f: {"label": "stayed"} for f in LAB_FIELDS}


# ----------------------------------------------------------------------
# Local backend (HuggingFace transformers, e.g. openai/gpt-oss-20b on MPS)
# ----------------------------------------------------------------------
JSON_INSTR = """
Respond with ONLY a single JSON object, no prose or markdown, of exactly this shape:
{
  "creatinine":  {"label": "<moved_into_range|stayed|moved_out_of_range>"},
  "bun":         {"label": "<...>"},
  "potassium":   {"label": "<...>"},
  "bicarbonate": {"label": "<...>"}
}
"""

def load_local(model_id):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading {model_id} on {dev} (dequantizing MXFP4->bf16; takes a few minutes)...",
          flush=True)
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16)
    model.to(dev)
    model.eval()
    print("Model loaded.", flush=True)
    return model, tok, dev


def _extract_json(text):
    """Parse the segment as JSON; else take the first OUTERMOST balanced {...}."""
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{": depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i + 1])
    raise ValueError("no parseable JSON object in generation")


def _final_channel(raw):
    """gpt-oss/harmony: keep only the assistant `final` channel message."""
    marker = "<|channel|>final<|message|>"
    seg = raw.rsplit(marker, 1)[-1] if marker in raw else raw
    for stop in ("<|return|>", "<|end|>", "<|start|>"):
        seg = seg.split(stop)[0]
    return seg


def predict_local(model, tok, dev, case, effort):
    import torch
    reasoning = effort if effort in ("low", "medium", "high") else "low"
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": build_prompt(case) + "\n" + JSON_INSTR},
    ]
    kw = dict(add_generation_prompt=True, return_tensors="pt", return_dict=True)
    try:
        enc = tok.apply_chat_template(messages, reasoning_effort=reasoning, **kw)
    except TypeError:
        enc = tok.apply_chat_template(messages, **kw)
    enc = {k: v.to(dev) for k, v in enc.items()}
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=1536, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    raw = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=False)
    obj = _extract_json(_final_channel(raw))
    result = {}
    for f in LAB_FIELDS:
        cell = obj.get(f) or {}
        lbl = cell.get("label")
        if lbl not in LABELS:
            raise ValueError(f"bad label for {f}: {lbl!r}")
        result[f] = {"label": lbl}
    return result


# ----------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------
def macro_f1(pairs):
    """pairs: list of (true, pred). Returns macro-F1 over the 3 classes."""
    f1s = []
    for c in LABELS:
        tp = sum(1 for t, p in pairs if t == c and p == c)
        fp = sum(1 for t, p in pairs if t != c and p == c)
        fn = sum(1 for t, p in pairs if t == c and p != c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(f1s) / len(f1s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(HERE, "cases_eligible_all4.jsonl"))
    ap.add_argument("--backend", default="anthropic", choices=["anthropic", "local"])
    ap.add_argument("--model", default=None,
                    help="model id; defaults to claude-opus-4-8 (anthropic) or openai/gpt-oss-20b (local)")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "results.jsonl"))
    args = ap.parse_args()
    if args.model is None:
        args.model = "openai/gpt-oss-20b" if args.backend == "local" else "claude-opus-4-8"

    cases = [json.loads(l) for l in open(args.cases)]
    if args.limit:
        cases = cases[:args.limit]
    print(f"Loaded {len(cases)} cases from {os.path.basename(args.cases)}")

    # ground-truth labels + majority baseline per lab
    truth = {f: {} for f in LAB_FIELDS}       # field -> hadm -> label
    for c in cases:
        for f, cname in LAB_FIELDS.items():
            truth[f][c["hadm_id"]] = c["outcome"]["targets"][cname]["label"]
    majority = {f: Counter(truth[f].values()).most_common(1)[0][0] for f in LAB_FIELDS}

    # run predictions
    results = {}   # hadm -> {field -> {label}}
    errors = 0
    if args.dry_run:
        for c in cases:
            results[c["hadm_id"]] = predict_dry(c)
    elif args.backend == "local":
        import time
        # crash-safe: append each finished case to a .partial sidecar; resume skips them.
        partial = args.out + ".partial"
        if os.path.exists(partial):
            for l in open(partial):
                try: row = json.loads(l)
                except Exception: continue
                h = row["hadm_id"]
                results[h] = {f: row["predictions"][cname]
                              for f, cname in LAB_FIELDS.items() if cname in row.get("predictions", {})}
            print(f"  resume: loaded {len(results)} completed cases from {os.path.basename(partial)}")
        todo = [c for c in cases if c["hadm_id"] not in results]
        print(f"  {len(todo)} cases to run ({len(results)} already done)")
        model, tok, dev = load_local(args.model)
        pf = open(partial, "a")
        t0 = time.monotonic()
        for i, c in enumerate(todo, 1):
            try:
                pred = predict_local(model, tok, dev, c, args.effort)
                results[c["hadm_id"]] = pred
                row = {"hadm_id": c["hadm_id"], "predictions": {}, "truth": {}, "correct": {}}
                for f, cname in LAB_FIELDS.items():
                    row["predictions"][cname] = pred[f]
                    row["truth"][cname] = truth[f][c["hadm_id"]]
                    row["correct"][cname] = (pred[f]["label"] == truth[f][c["hadm_id"]])
                pf.write(json.dumps(row) + "\n"); pf.flush()
            except Exception as e:
                errors += 1
                print(f"  ! error on {c['hadm_id']}: {e}", file=sys.stderr)
            el = time.monotonic() - t0
            rate = el / i
            print(f"  {i}/{len(todo)} done ({errors} err)  "
                  f"{rate:.1f}s/case  eta {rate*(len(todo)-i)/60:.0f}min", flush=True)
        pf.close()
    else:
        import anthropic
        client = anthropic.Anthropic()

        def work(c):
            return c["hadm_id"], predict_live(client, c, args.model, args.effort)

        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(work, c): c for c in cases}
            for fut in as_completed(futs):
                try:
                    hadm, pred = fut.result()
                    results[hadm] = pred
                except Exception as e:
                    errors += 1
                    print(f"  ! error on {futs[fut]['hadm_id']}: {e}", file=sys.stderr)
                done += 1
                if done % 10 == 0 or done == len(cases):
                    print(f"  {done}/{len(cases)} done ({errors} errors)")

    # write per-case results
    with open(args.out, "w") as fo:
        for c in cases:
            hadm = c["hadm_id"]
            if hadm not in results:
                continue
            row = {"hadm_id": hadm, "predictions": {}, "truth": {}}
            for f, cname in LAB_FIELDS.items():
                pred = results[hadm][f]
                row["predictions"][cname] = pred
                row["truth"][cname] = truth[f][hadm]
                row.setdefault("correct", {})[cname] = (pred["label"] == truth[f][hadm])
            fo.write(json.dumps(row) + "\n")

    # ---- report ----
    print("\n===================== RESULTS =====================")
    print(f"model={'DRY-RUN' if args.dry_run else args.model}"
          f"{'' if args.dry_run else ' effort='+args.effort}  cases scored={len(results)}")
    print(f"\n{'lab':>20} | {'acc':>6} {'majB':>6} {'lift':>6} | {'macroF1':>7} | into/stayed/out (true)")
    print("-" * 82)
    overall_pairs = []
    for f, cname in LAB_FIELDS.items():
        pairs = [(truth[f][h], results[h][f]["label"]) for h in results]
        overall_pairs += pairs
        acc = sum(1 for t, p in pairs if t == p) / len(pairs)
        majacc = sum(1 for t, _ in pairs if t == majority[f]) / len(pairs)
        dist = Counter(t for t, _ in pairs)
        print(f"{cname:>20} | {acc:6.3f} {majacc:6.3f} {acc-majacc:+6.3f} | "
              f"{macro_f1(pairs):7.3f} | "
              f"{dist['moved_into_range']}/{dist['stayed']}/{dist['moved_out_of_range']}")
    oacc = sum(1 for t, p in overall_pairs if t == p) / len(overall_pairs)
    print("-" * 82)
    print(f"{'OVERALL (4 labs)':>20} | {oacc:6.3f} {'':>6} {'':>6} | {macro_f1(overall_pairs):7.3f} |")
    print(f"\nMajority-class baseline per lab: "
          + ", ".join(f"{c}={majority[f]}" for f, c in LAB_FIELDS.items()))
    print(f"Wrote per-case results -> {args.out}")


if __name__ == "__main__":
    main()
