#!/usr/bin/env python3
"""
Model-readiness sweep for the Version_3 deck on the current 3x TITAN Xp node.
Loads each FEASIBLE model (fp16, device_map=auto across the 3 GPUs), runs a
short generation, and records status/timing/peak-mem. Big models that cannot
run on 36GB Pascal are skipped with a reason. Writes JSON + text log.
"""
import gc, json, os, time, traceback
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = "/scratch/users/karun09/Version_3/SIMR-Research/Version_3/loaded_models"
OUT_JSON = "/scratch/users/karun09/Version_3/smoke_readiness.json"

# (key, run?, reason-if-skipped)
PLAN = [
    ("phi-4-mini",        True,  ""),
    ("qwen3-8b",          True,  ""),
    ("llama-3.1-8b",      True,  ""),
    ("gemma-4-e4b",       True,  ""),
    ("mistral-small-3.1", False, "24B bf16 ~48GB > 36GB total; 4-bit needs bitsandbytes (broken + CC6.1<7.5)"),
    ("gpt-oss-20b",       False, "MoE/mxfp4 kernels unsupported on Pascal (CC 6.1)"),
    ("clmbr-t-base",      False, "EHR foundation model, not a causal LM (use FEMR/meds_reader)"),
]
PROMPT = "In one sentence, what is acute kidney injury?"
results = []

def free():
    gc.collect(); torch.cuda.empty_cache()
    for i in range(torch.cuda.device_count()):
        try:
            torch.cuda.reset_peak_memory_stats(i)
        except Exception:
            pass  # no CUDA context on this device yet

for key, run, reason in PLAN:
    if not run:
        print(f"\n### SKIP {key}: {reason}", flush=True)
        results.append({"key": key, "status": "skipped", "reason": reason})
        continue
    path = os.path.join(BASE, key)
    print(f"\n### RUN {key}  ({path})", flush=True)
    rec = {"key": key, "status": "?", "path": path}
    free()
    try:
        t0 = time.time()
        tok = AutoTokenizer.from_pretrained(path)
        model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float16, device_map="auto")
        rec["load_s"] = round(time.time() - t0, 1)
        enc = tok.apply_chat_template([{"role": "user", "content": PROMPT}],
                                      add_generation_prompt=True, return_tensors="pt",
                                      return_dict=True).to(model.device)
        in_len = enc["input_ids"].shape[-1]
        t1 = time.time()
        out = model.generate(**enc, max_new_tokens=48, do_sample=False)
        rec["gen_s"] = round(time.time() - t1, 1)
        rec["new_tokens"] = int(out.shape[-1] - in_len)
        rec["output"] = tok.decode(out[0][in_len:], skip_special_tokens=True).strip()
        rec["peak_mem_gb"] = round(sum(torch.cuda.max_memory_allocated(i)
                                       for i in range(torch.cuda.device_count())) / 1e9, 2)
        rec["devices"] = str(model.hf_device_map) if hasattr(model, "hf_device_map") else "cuda"
        rec["status"] = "PASS"
        print(f"  PASS load={rec['load_s']}s gen={rec['gen_s']}s peak={rec['peak_mem_gb']}GB", flush=True)
        print(f"  -> {rec['output'][:160]}", flush=True)
        del model, tok
    except Exception as e:
        rec["status"] = "FAIL"
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["trace"] = traceback.format_exc()[-800:]
        print(f"  FAIL {rec['error']}", flush=True)
    results.append(rec)
    free()

with open(OUT_JSON, "w") as f:
    json.dump(results, f, indent=2)

print("\n===== SUMMARY =====", flush=True)
for r in results:
    line = f"{r['key']:20s} {r['status']:8s}"
    if r["status"] == "PASS":
        line += f" load={r.get('load_s')}s gen={r.get('gen_s')}s peak={r.get('peak_mem_gb')}GB"
    elif r["status"] == "skipped":
        line += f" ({r['reason']})"
    elif r["status"] == "FAIL":
        line += f" {r.get('error')}"
    print(line, flush=True)
print(f"\nJSON -> {OUT_JSON}", flush=True)
