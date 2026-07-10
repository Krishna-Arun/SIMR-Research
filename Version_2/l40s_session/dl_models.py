import os, sys, time
from huggingface_hub import snapshot_download
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
MODELS = ["NousResearch/Meta-Llama-3.1-8B-Instruct", "microsoft/Phi-3-small-8k-instruct"]
for m in MODELS:
    t = time.time()
    print(f"[dl] {m} ...", flush=True)
    # skip the heavy duplicate formats; keep safetensors + configs + tokenizer
    p = snapshot_download(m, allow_patterns=["*.safetensors","*.json","*.txt","*.model","*.py","*.tiktoken","tokenizer*"])
    print(f"[ok] {m} -> {p}  ({time.time()-t:.0f}s)", flush=True)
print("[done] all models present", flush=True)
