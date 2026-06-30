"""Smoke test the swapped models on the L40S via the real qgen HF backend."""
import os, sys, time
os.environ.setdefault("HF_HOME", os.path.expandvars("$SCRATCH/.huggingface"))
os.environ.setdefault("HF_HUB_CACHE", os.path.expandvars("$SCRATCH/.huggingface/hub"))
sys.path.insert(0, "/scratch/users/karun09/Version_2/Benchmark_A/Question_Generation")
import yaml
from qgen.hf_backend import make_chat

cfg = yaml.safe_load(open("/scratch/users/karun09/Version_2/Benchmark_A/Question_Generation/config/qgen_pilot.yaml"))
for role in ("optimizer", "evaluator"):
    rc = dict(cfg["models"][role]); rc["max_tokens"] = 64
    print(f"\n==== {role}: {rc['model_id']} ====", flush=True)
    t = time.time()
    chat = make_chat(rc)
    print(f"  loaded in {time.time()-t:.0f}s, healthy={chat.healthy()}", flush=True)
    t = time.time()
    out = chat.chat([{"role":"user","content":"Reply with exactly the word: READY"}], temperature=0.0)
    print(f"  gen in {time.time()-t:.1f}s -> {out.text!r}", flush=True)
print("\n[SMOKE OK] both models load + generate on the L40S", flush=True)
