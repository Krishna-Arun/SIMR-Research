import json, os, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from evaluate import build_prompt, SYSTEM, JSON_INSTR

case = json.loads(open("cases_eligible_all4.jsonl").readline())
tok = AutoTokenizer.from_pretrained("openai/gpt-oss-20b")
model = AutoModelForCausalLM.from_pretrained("openai/gpt-oss-20b", dtype=torch.bfloat16).to("mps").eval()

msgs = [{"role": "system", "content": SYSTEM},
        {"role": "user", "content": build_prompt(case) + "\n" + JSON_INSTR}]
inp = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                              reasoning_effort="low").to("mps")
with torch.no_grad():
    out = model.generate(inp, max_new_tokens=1024, do_sample=False, pad_token_id=tok.eos_token_id)
raw = tok.decode(out[0][inp.shape[1]:], skip_special_tokens=False)
print("===== RAW (special tokens kept) =====")
print(raw)
print("\n===== decoded (skip_special) =====")
print(tok.decode(out[0][inp.shape[1]:], skip_special_tokens=True))
