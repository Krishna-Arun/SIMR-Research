"""run_arm.py — run one ablation arm for one model over the cf_questions set.

Arms:
  vanilla        Arm 1  — served prompt only, no world model
  text_frozen    Arm 2a — + serialized SIMULATOR EVIDENCE block, frozen LLM
  text_sft       Arm 3a — text evidence + a LoRA adapter (path via --adapter)
  latent_frozen  Arm 2b — injected virtual tokens, frozen LLM + trained projector   (M2)
  latent_sft     Arm 3b — injected tokens + LoRA                                     (M3)

For M1 only `vanilla` is wired; the text arms use evidence_for() (rollout_api + serialize_rollout),
the latent arms are handled by cf_llm_model (built in M2/M3). The served prompt is byte-identical across
arms except for the appended evidence block (fairness invariant).

Run: simr python run_arm.py --arm vanilla --model gemma-4-e4b [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
HERE = Path(__file__).resolve().parent
BACKEND_DIR = Path("/scratch/users/karun09/Version_3/SIMR-Research/Version_3/Benchmark_A/Question_Gen")
# HERE must win for local modules (prompts/serialize_rollout/rollout_api) — the benchmark dir ALSO has a
# prompts.py, so we import backend by file path (below) rather than putting BACKEND_DIR on sys.path.
for p in (str(BASE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import prompts as P  # noqa: E402
from build_cf_questions import served_view  # noqa: E402 (reuse the whitelist)


def _load_backend():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bm_backend", BACKEND_DIR / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.LocalLLM


def chat_robust(llm, messages, max_new_tokens=512):
    """Greedy generation robust to (a) chat templates that return a dict/BatchEncoding vs a tensor,
    (b) multimodal-ish tokenizers. Uses the backend's lazy loader but bypasses its chat() templating."""
    import torch
    llm._ensure_loaded()
    tok, model = llm._tok, llm._model
    try:
        enc = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
    except Exception:
        # some templates (e.g. Gemma) reject a separate system role — merge it into the first user turn
        merged, sys_txt = [], ""
        for m in messages:
            if m["role"] == "system":
                sys_txt += m["content"] + "\n\n"
            elif m["role"] == "user" and sys_txt:
                merged.append({"role": "user", "content": sys_txt + m["content"]})
                sys_txt = ""
            else:
                merged.append(m)
        enc = tok.apply_chat_template(merged, add_generation_prompt=True, return_tensors="pt")
    if isinstance(enc, dict) or hasattr(enc, "input_ids"):
        input_ids = enc["input_ids"]
        attn = enc.get("attention_mask")
    else:
        input_ids = enc
        attn = None
    input_ids = input_ids.to(model.device)
    kw = {"max_new_tokens": max_new_tokens, "do_sample": False,
          "pad_token_id": tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id}
    if attn is not None:
        kw["attention_mask"] = attn.to(model.device)
    with torch.no_grad():
        out = model.generate(input_ids, **kw)
    return tok.decode(out[0][input_ids.shape[-1]:], skip_special_tokens=True).strip()

QFILE = HERE / "outputs/cf_questions.jsonl"
ANS_RE = re.compile(r"ANSWER:\s*([A-Za-z]+)", re.IGNORECASE)
CONF_RE = re.compile(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def render_prompt(rec: dict, evidence: str | None) -> str:
    pf = rec["prompt_fields"]
    if rec["family"] == "A":
        def pcase(tag, c):
            return (f"Patient {tag}:\n"
                    f"  Baseline labs: {', '.join(f'{k} {v:g}' for k,v in c['baseline_labs'].items())}\n"
                    f"  Labs ~{c['hours_observed']:g}h later: "
                    f"{', '.join(f'{k} {v:g}' for k,v in c['later_labs'].items())}")
        case = "TWO ICU PATIENTS (treatments hidden):\n" + pcase("A", pf["patient_A"]) + "\n\n" + \
               pcase("B", pf["patient_B"])
    else:
        case = P.case_block(pf["baseline_labs"], pf.get("active_meds"),
                            pf.get("demographics"), pf.get("reveal_meds", True))
    return P.build_prompt(case, pf["question"], evidence=evidence)


def parse_answer(text: str, choices: list) -> "tuple[str|None, float|None]":
    m = ANS_RE.search(text)
    ans = None
    if m:
        tok = m.group(1).strip().lower()
        for c in choices:
            if c.lower() == tok or c.lower().startswith(tok) or tok.startswith(c.lower()):
                ans = c
                break
    cm = CONF_RE.search(text)
    conf = None
    if cm:
        try:
            conf = max(0.0, min(1.0, float(cm.group(1))))
        except ValueError:
            conf = None
    return ans, conf


def make_evidence_fn(arm: str):
    """Return evidence_for(rec)->str|None. Vanilla + latent arms => None (latent handled in the model)."""
    if arm in ("vanilla", "latent_frozen", "latent_sft"):
        return lambda rec: None
    # text arms: lazily build the rollout engine once
    import rollout_api as R
    engine = {"e": None}

    def evidence_for(rec):
        if engine["e"] is None:
            engine["e"] = R.load_engine()
        return _text_evidence(engine["e"], rec, R)

    return evidence_for


def _text_evidence(eng, rec, R):
    import pickle
    import numpy as np
    import serialize_rollout as S
    if not hasattr(_text_evidence, "_sub"):
        _text_evidence._sub = {int(e["patient_id"]): e
                               for e in pickle.load(open(BASE / "data/train_substrate.pkl", "rb"))}
    sub = _text_evidence._sub
    cc = rec["candidate_context"]
    if rec["family"] == "A":  # simulate both patients' factual forecast
        blocks = []
        for tag in ("A", "B"):
            e = sub[cc[f"patient_id_{tag}"]]
            out = R.rollout_from_entry(eng, e, horizon=3,
                                       plans={"factual": np.asarray(e["action_matrix"])[1:4]})
            blocks.append(f"[Patient {tag} forecast]\n" + S.serialize(out))
        return "\n\n".join(blocks)
    e = sub[cc["patient_id"]]
    out = R.rollout_from_entry(eng, e, horizon=3)
    return S.serialize(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True,
                    choices=["vanilla", "text_frozen", "text_sft", "latent_frozen", "latent_sft"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--max_new_tokens", type=int, default=512)
    ap.add_argument("--load_in_4bit", action="store_true")
    ap.add_argument("--adapter", default=None, help="fusion dir with projector.pt (+lora) for latent arms")
    ap.add_argument("--placebo", action="store_true", help="latent arms: inject a MISMATCHED patient pack")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(QFILE)]
    if args.limit:
        recs = recs[:args.limit]
    is_latent = args.arm in ("latent_frozen", "latent_sft")

    if is_latent:
        import torch
        from cf_llm_model import WorldModelInjectedLM
        wm = WorldModelInjectedLM(args.model, use_lora=(args.arm == "latent_sft"))
        if args.adapter:
            wm.load_trainables(args.adapter)
        else:
            print("WARNING: no --adapter; projector is UNTRAINED (random-projector floor / control C2)")
        packs = torch.load(HERE / "outputs/cf_qa_test_packs.pt", weights_only=False)
        if args.placebo:  # mismatched-latent leakage guard: rotate pack assignment among B/C qids
            keys = [r["qid"] for r in recs if r["qid"] in packs]
            packs = {keys[i]: packs[keys[(i + 1) % len(keys)]] for i in range(len(keys))}

        def skip(rec):
            return rec["qid"] not in packs  # latent route = B/C only (single-patient packs)

        def gen(rec):
            msgs = [{"role": "system", "content": P.SYSTEM_PROMPT},
                    {"role": "user", "content": render_prompt(rec, None)}]
            return wm.generate(packs[rec["qid"]], msgs, max_new_tokens=args.max_new_tokens)
    else:
        LocalLLM = _load_backend()
        llm = LocalLLM(args.model, load_in_4bit=args.load_in_4bit)
        evidence_for = make_evidence_fn(args.arm)

        def skip(rec):
            return False

        def gen(rec):
            user = render_prompt(rec, evidence_for(rec))
            return chat_robust(llm, [{"role": "system", "content": P.SYSTEM_PROMPT},
                                     {"role": "user", "content": user}],
                               max_new_tokens=args.max_new_tokens)

    outp = Path(args.out) if args.out else HERE / f"outputs/preds_{args.arm}_{args.model}.jsonl"
    outp.parent.mkdir(parents=True, exist_ok=True)
    n = n_ok = n_parsefail = 0
    with open(outp, "w") as f:
        for rec in recs:
            _ = served_view(rec)  # assert no leak before we render
            if skip(rec):
                continue
            reply = gen(rec)
            ans, conf = parse_answer(reply, rec["choices"])
            n += 1
            if ans is None:
                n_parsefail += 1
            correct = (ans == rec["answer"])
            n_ok += int(correct)
            f.write(json.dumps({
                "qid": rec["qid"], "family": rec["family"], "arm": args.arm, "model": args.model,
                "pred": ans, "confidence": conf, "gold": rec["answer"], "correct": bool(correct),
                "meta": rec.get("meta", {}), "reply": reply,
            }) + "\n")
            if n % 25 == 0:
                print(f"  {n} done  running acc={n_ok/n:.3f} parsefail={n_parsefail}", flush=True)

    print(f"\narm={args.arm} model={args.model}  n={n}  "
          f"raw_acc={n_ok/max(n,1):.3f}  parse_fail={n_parsefail}")
    print(f"wrote {outp}")


if __name__ == "__main__":
    main()
