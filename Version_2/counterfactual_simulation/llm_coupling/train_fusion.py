"""train_fusion.py — Route B training.

arm latent_frozen (2b): train the projector only, LLM frozen.
arm latent_sft    (3b): train projector + LoRA (peft), LLM base frozen.

Trains on cf_qa_train (family B+C, single-patient) with answer-span cross-entropy; the injected latents
are the only world-model signal, labels are observed/known-arrow (anti-circularity intact). Greedy val
accuracy each epoch; saves best trainables (projector.pt + optional lora_adapter/) under --out.

Run (GPU batch): simr python train_fusion.py --model qwen3-8b --arm latent_frozen --epochs 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
HERE = Path(__file__).resolve().parent
for p in (str(BASE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import prompts as P  # noqa: E402
from cf_llm_model import WorldModelInjectedLM  # noqa: E402
from run_arm import parse_answer  # noqa: E402

OUT = HERE / "outputs"


def render_bc(rec):
    pf = rec["prompt_fields"]
    case = P.case_block(pf["baseline_labs"], pf.get("active_meds"), pf.get("demographics"),
                        pf.get("reveal_meds", True))
    user = P.build_prompt(case, pf["question"], evidence=None)
    return [{"role": "system", "content": P.SYSTEM_PROMPT}, {"role": "user", "content": user}]


def load_split(split):
    recs = [json.loads(l) for l in open(OUT / f"cf_qa_{split}.jsonl")]
    packs = torch.load(OUT / f"cf_qa_{split}_packs.pt", weights_only=False)
    return [r for r in recs if r["qid"] in packs], packs


@torch.no_grad()
def evaluate(wm, recs, packs, max_new_tokens=64, limit=120):
    wm.model.eval()
    n = ok = 0
    for r in recs[:limit]:
        reply = wm.generate(packs[r["qid"]], render_bc(r), max_new_tokens=max_new_tokens)
        pred, _ = parse_answer(reply, r["choices"])
        ok += int(pred == r["answer"]); n += 1
    return ok / max(n, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--arm", choices=["latent_frozen", "latent_sft"], default="latent_frozen")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    use_lora = args.arm == "latent_sft"
    wm = WorldModelInjectedLM(args.model, use_lora=use_lora)
    wm.model.config.use_cache = False
    try:
        wm.model.gradient_checkpointing_enable()
    except Exception as e:
        print("grad-checkpointing unavailable:", e)

    tr, trp = load_split("train")
    va, vap = load_split("val")
    print(f"train={len(tr)} val={len(va)}  arm={args.arm} model={args.model}")

    params = wm.trainable_parameters()
    n_par = sum(p.numel() for p in params)
    print(f"trainable params: {n_par/1e6:.2f}M")
    opt = torch.optim.AdamW(params, lr=args.lr)

    outdir = Path(args.out) if args.out else OUT / f"fusion_{args.arm}_{args.model}"
    best = -1.0
    rng = torch.Generator().manual_seed(0)
    for ep in range(args.epochs):
        wm.model.train()
        order = torch.randperm(len(tr), generator=rng).tolist()
        opt.zero_grad()
        run = 0.0
        for step, start in enumerate(range(0, len(order), args.batch)):
            idx = order[start:start + args.batch]
            recs = [tr[i] for i in idx]
            out = wm([trp[r["qid"]] for r in recs], [render_bc(r) for r in recs],
                     [r["answer"] for r in recs])
            loss = out.loss / args.accum
            loss.backward()
            run += float(out.loss)
            if (step + 1) % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                opt.step(); opt.zero_grad()
            if (step + 1) % 50 == 0:
                print(f"  ep{ep} step{step+1} avg_loss={run/(step+1):.4f}", flush=True)
        acc = evaluate(wm, va, vap)
        print(f"[epoch {ep}] train_loss={run/max(1,len(order)//args.batch):.4f}  val_acc={acc:.3f}",
              flush=True)
        if acc >= best:
            best = acc
            wm.save_trainables(outdir)
            print(f"  saved best (val_acc={acc:.3f}) -> {outdir}")
    print(f"DONE best_val_acc={best:.3f} out={outdir}")


if __name__ == "__main__":
    main()
