#!/usr/bin/env python3
"""
GRPO training scaffold for the CounterfactualSim RL environment (CLUSTER entry).

Trains a policy to answer the longitudinal benchmark, rewarded by the SAME scorer
used everywhere else (Longitudinal/score_longitudinal.score_case). During rollouts
the simulate() MCP tool is available as a counterfactual world-model oracle.

  --smoke : verify imports + build the prompt dataset object and print its size,
            WITHOUT launching training (runs on a laptop, no GPU).
  real    : launch trl.GRPOTrainer on the GPU cluster.

Heavy deps (torch/trl/datasets) are imported lazily so `python -m py_compile`
and `--smoke` degrade gracefully with a clear message.

  python rl_env/train_grpo.py --smoke
  python rl_env/train_grpo.py --model qwen3:4b --epochs 1 --output_dir ./grpo_out
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── repo layout (mirror ablation.py) ─────────────────────────────────────────
HERE = Path(__file__).resolve()
CFSIM_DIR = HERE.parent.parent
V3_DIR = CFSIM_DIR.parent
LONG_DIR = V3_DIR / "Longitudinal"
QGEN_DIR = V3_DIR / "Benchmark_A" / "Question_Gen"

JSONL = LONG_DIR / "outputs" / "longitudinal.jsonl"
ANSWERING_DIR = LONG_DIR / "outputs" / "answering"

_ANSWER_SPEC = (
    "You are answering a multi-step longitudinal ICU question. Reply with ONE JSON "
    "object with the keys for the steps present, e.g. "
    '{"A1": ["<option>"], "C": "A", "B": {"<lab>": "Rising|Falling|Stable"}, '
    '"A2": ["<option>"]}. Use option text verbatim; predict every listed lab in B. '
    "Output only the JSON."
)


# ── dataset: one prompt per benchmark case (answering view), keep the record ──
def build_examples() -> list:
    """List of {question_id, prompt, record} — record carries the answer keys
    that the reward function grades against (never shown to the policy)."""
    if not JSONL.exists():
        raise FileNotFoundError(f"benchmark not found: {JSONL}")
    records = {}
    with open(JSONL) as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                records[r["question_id"]] = r

    examples = []
    for qid, record in records.items():
        view_path = ANSWERING_DIR / f"{qid}.json"
        if not view_path.exists():
            continue
        with open(view_path) as f:
            view = json.load(f)
        case = {"question_id": qid, "steps": view.get("steps", {})}
        prompt = _ANSWER_SPEC + "\n\nCASE:\n" + json.dumps(case)[:12000]
        examples.append({"question_id": qid, "prompt": prompt, "record": record})
    return examples


class _ListDataset(list):
    """Minimal stdlib stand-in for a HF Dataset so --smoke runs offline."""
    def __init__(self, rows):
        super().__init__(rows)


def build_dataset(require_hf: bool = True):
    """Wrap the examples in a HF Dataset (lazy import). When `require_hf` is
    False (smoke on a laptop), fall back to a plain list-backed dataset."""
    examples = build_examples()
    try:
        from datasets import Dataset
    except Exception as e:                           # pragma: no cover
        if require_hf:
            raise ImportError(
                "`datasets` is required to launch training "
                f"(install on the cluster): {e}")
        print(f"[smoke] `datasets` unavailable ({e}); using a stdlib list dataset.")
        return _ListDataset(examples), examples
    # GRPOTrainer consumes the `prompt` column; we carry record/qid alongside so
    # the reward function can look up the answer keys by index.
    return Dataset.from_list(examples), examples


# ── reward function: parse completion -> answers -> score_case()["total"] ─────
def make_reward_fn(examples: list):
    from score_longitudinal import score_case        # pure stdlib
    from ablation import parse_reply                  # reuse the tolerant parser

    by_qid = {ex["question_id"]: ex["record"] for ex in examples}

    def reward_fn(prompts=None, completions=None, question_id=None, **kwargs):
        """trl passes columns as kwargs; `question_id` lets us fetch the record.
        Returns one float reward per completion in [0, 1]."""
        rewards = []
        for i, completion in enumerate(completions or []):
            qid = question_id[i] if question_id else None
            record = by_qid.get(qid)
            text = completion if isinstance(completion, str) else str(completion)
            if record is None:
                rewards.append(0.0)
                continue
            view = {"question_id": qid, "steps": record.get("steps", {})}
            answers = parse_reply(text, view)
            rewards.append(float(score_case(record, answers)["total"]))
        return rewards

    return reward_fn


# ── training ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="GRPO trainer scaffold (cluster)")
    ap.add_argument("--smoke", action="store_true",
                    help="verify imports + build dataset and print its size; no training")
    ap.add_argument("--model", default="qwen3:4b", help="base model id / HF repo")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--output_dir", default="./grpo_out")
    args = ap.parse_args()

    sys.path.insert(0, str(LONG_DIR))                # score_longitudinal
    sys.path.insert(0, str(HERE.parent))             # ablation.parse_reply

    dataset, examples = build_dataset(require_hf=not args.smoke)
    print(f"Built prompt dataset: {len(dataset)} example(s) from {JSONL}")

    if args.smoke:
        # sanity-check the reward on the first example against itself
        reward_fn = make_reward_fn(examples)
        if examples:
            demo = reward_fn(completions=["{}"], question_id=[examples[0]["question_id"]])
            print(f"Reward smoke (empty answer -> trivial baseline): {demo}")
        print("[smoke] imports OK, dataset built — NOT launching training.")
        return 0

    # ── real training (GPU cluster) ──────────────────────────────────────────
    try:
        from trl import GRPOConfig, GRPOTrainer
    except Exception as e:                           # pragma: no cover
        print("[error] trl is not installed. On the cluster: `pip install trl`.\n"
              f"        Import error: {e}")
        return 1

    reward_fn = make_reward_fn(examples)
    config = GRPOConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        num_generations=4,
        max_prompt_length=4096,
        max_completion_length=1200,
        logging_steps=1,
    )
    # TODO(cluster): enable native tool-calling in rollouts so the policy can call
    #   simulate() (CounterfactualSim/simulate_server.py) mid-generation. Until the
    #   world-model checkpoint is trained ($CFSIM_CKPT), simulate() serves heuristic
    #   priors; point CFSIM_CKPT at the trained checkpoint to reward against calibrated
    #   counterfactuals. GRPO output_dir here becomes ablation.py's $GRPO_CKPT.
    trainer = GRPOTrainer(
        model=args.model,
        reward_funcs=reward_fn,
        args=config,
        train_dataset=dataset,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    print(f"Saved GRPO model to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
