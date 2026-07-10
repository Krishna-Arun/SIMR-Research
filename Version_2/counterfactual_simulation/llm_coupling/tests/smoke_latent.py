"""smoke_latent.py — validate the Route-B plumbing on a small model (phi-4-mini) end-to-end:
projector shapes, inputs_embeds injection, answer-span loss + grad flow (projector trains, backbone
frozen), and generation. Runs on a small GPU."""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
BASE = Path("/scratch/users/karun09/Version_2/counterfactual_simulation")
for p in (str(HERE.parent), str(BASE)):
    sys.path.insert(0, p)

import rollout_api as R  # noqa
import prompts as P  # noqa
from cf_llm_model import WorldModelInjectedLM  # noqa
from run_arm import parse_answer  # noqa


def main():
    torch.manual_seed(0)
    eng = R.load_engine()
    sub = pickle.load(open(BASE / "data/train_substrate.pkl", "rb"))
    sp = json.loads((BASE / "data/splits.json").read_text())["splits"]
    test = set(sp["test"])
    e = next(x for x in sub if int(x["patient_id"]) in test and x["s"].shape[0] >= 4)
    pack = R.build_latent_pack(eng, e, tz_index=0, horizon=3)
    print(f"pack: z_now{pack['z_now'].shape} z_hist{np.asarray(pack['z_hist']).shape} "
          f"cf_plans={list(pack['cf'])}")

    wm = WorldModelInjectedLM("phi-4-mini", use_lora=False)
    wm.model.config.use_cache = False
    try:
        wm.model.gradient_checkpointing_enable()
    except Exception as ex:
        print("gc off:", ex)

    emb, roles = wm.projector.encode_one(pack)
    print(f"projected tokens: emb{tuple(emb.shape)} roles={roles.tolist()}  "
          f"rms={float(emb.pow(2).mean().sqrt()):.3f} (target {float(wm.projector.target_rms):.3f})")

    # two tiny training examples
    def msgs(q):
        case = P.case_block({"creatinine": 1.4, "bun": 40, "potassium": 5.2}, ["furosemide_iv"],
                            "cardiac ICU")
        return [{"role": "system", "content": P.SYSTEM_PROMPT},
                {"role": "user", "content": P.build_prompt(case, q, evidence=None)}]

    packs = [pack, pack]
    ml = [msgs("if we were to add dialysis, would the patient's creatinine be Higher, Lower, or Unchanged?"),
          msgs("how will potassium trend: Rising, Falling, or Stable?")]
    answers = ["Lower", "Falling"]

    out = wm(packs, ml, answers)
    print(f"forward loss={float(out.loss):.4f}")
    out.loss.backward()
    proj_grad = sum(float(p.grad.abs().sum()) for p in wm.projector.parameters() if p.grad is not None)
    base_grad_params = [p for p in wm.model.parameters() if p.requires_grad]
    print(f"projector grad-sum={proj_grad:.3f} (should be >0);  trainable backbone params="
          f"{len(base_grad_params)} (should be 0)")
    assert proj_grad > 0, "projector received no gradient"
    assert len(base_grad_params) == 0, "backbone not fully frozen"

    reply = wm.generate(pack, ml[0], max_new_tokens=48)
    pred, conf = parse_answer(reply, ["Higher", "Lower", "Unchanged"])
    print(f"\ngenerate -> pred={pred} conf={conf}\nreply[:200]={reply[:200]!r}")
    print("\nSMOKE OK")


if __name__ == "__main__":
    main()
