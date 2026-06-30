import time
from huggingface_hub import snapshot_download
t=time.time()
p=snapshot_download("microsoft/phi-4", allow_patterns=["*.safetensors","*.json","*.txt","*.model","tokenizer*"])
print(f"[ok] microsoft/phi-4 -> {p} ({time.time()-t:.0f}s)", flush=True)
print("[done]", flush=True)
