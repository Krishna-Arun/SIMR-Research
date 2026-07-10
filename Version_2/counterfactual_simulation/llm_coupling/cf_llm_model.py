"""cf_llm_model.py — Route B: WorldModelInjectedLM.

Wraps a HF causal LM and prepends the WorldModelProjector's virtual tokens to the text in EMBEDDING
space (LLaVA-style, via inputs_embeds). Backbone is always frozen; trainables are:
  arm 2b  -> projector only
  arm 3b  -> projector + LoRA adapters (peft)

Provides training_batch() (padded inputs_embeds + attention_mask + answer-span labels) and generate().
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import torch
import torch.nn as nn

from cf_projector import WorldModelProjector

BACKEND = Path("/scratch/users/karun09/Version_3/SIMR-Research/Version_3/Benchmark_A/Question_Gen/backend.py")


def _resolve_source(model_key: str) -> str:
    spec = importlib.util.spec_from_file_location("bm_backend", BACKEND)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._resolve_source(model_key)


def _apply_template(tok, messages, add_generation_prompt=True):
    """Return prompt token ids [1,t] robust to dict-return templates + system-role rejection."""
    def go(msgs):
        return tok.apply_chat_template(msgs, add_generation_prompt=add_generation_prompt,
                                       return_tensors="pt")
    try:
        enc = go(messages)
    except Exception:
        merged, sys_txt = [], ""
        for m in messages:
            if m["role"] == "system":
                sys_txt += m["content"] + "\n\n"
            elif m["role"] == "user" and sys_txt:
                merged.append({"role": "user", "content": sys_txt + m["content"]}); sys_txt = ""
            else:
                merged.append(m)
        enc = go(merged)
    if isinstance(enc, dict) or hasattr(enc, "input_ids"):
        return enc["input_ids"]
    return enc


class WorldModelInjectedLM(nn.Module):
    def __init__(self, model_key: str, hist: int = 3, use_lora: bool = False,
                 lora_r: int = 16, lora_alpha: int = 32, lora_dropout: float = 0.05,
                 dtype=torch.bfloat16, device_map="auto"):
        super().__init__()
        from transformers import AutoModelForCausalLM, AutoTokenizer
        src = _resolve_source(model_key)
        self.tok = AutoTokenizer.from_pretrained(src)
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(src, dtype=dtype, device_map=device_map)
        for p in self.model.parameters():
            p.requires_grad_(False)
        if use_lora:
            from peft import LoraConfig, get_peft_model
            cfg = LoraConfig(r=lora_r, lora_alpha=lora_alpha, lora_dropout=lora_dropout, bias="none",
                             task_type="CAUSAL_LM",
                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                             "gate_proj", "up_proj", "down_proj"])
            self.model = get_peft_model(self.model, cfg)
        self.use_lora = use_lora
        emb = self.model.get_input_embeddings()
        H = emb.weight.shape[1]
        # RMS on a row sample (full-matrix fp32 upcast can OOM a small GPU)
        w = emb.weight.detach()
        w = w[:8192] if w.shape[0] > 8192 else w
        rms = float(w.float().pow(2).mean().sqrt())
        self.projector = WorldModelProjector(H, hist=hist, target_rms=rms).to(emb.weight.device,
                                                                              dtype=dtype)
        self.dtype = dtype

    # ---- helpers ----
    @property
    def device(self):
        return self.model.get_input_embeddings().weight.device

    def trainable_parameters(self):
        ps = list(self.projector.parameters())
        if self.use_lora:
            ps += [p for p in self.model.parameters() if p.requires_grad]
        return ps

    def _text_embed(self, ids):
        return self.model.get_input_embeddings()(ids.to(self.device))

    def _wm_embed(self, pack):
        emb, _ = self.projector.encode_one(pack, device=self.device)
        return emb  # [k,H]

    # ---- training ----
    def training_batch(self, packs, messages_list, answers):
        """Build padded (inputs_embeds, attention_mask, labels). Answer-span-only loss; wm+prompt=-100."""
        seqs, labs = [], []
        for pack, messages, ans in zip(packs, messages_list, answers):
            pid = _apply_template(self.tok, messages)[0].to(self.device)              # [t]
            aid = self.tok(ans + self.tok.eos_token, add_special_tokens=False,
                           return_tensors="pt")["input_ids"][0].to(self.device)        # [a]
            wm = self._wm_embed(pack)                                                  # [k,H]
            txt = self._text_embed(torch.cat([pid, aid]))                              # [t+a,H]
            seq = torch.cat([wm, txt], 0)                                              # [k+t+a,H]
            lab = torch.full((seq.shape[0],), -100, dtype=torch.long, device=self.device)
            lab[wm.shape[0] + pid.shape[0]:] = torch.cat([pid, aid])[pid.shape[0]:]
            seqs.append(seq); labs.append(lab)
        L = max(s.shape[0] for s in seqs)
        H = seqs[0].shape[1]
        B = len(seqs)
        inp = torch.zeros(B, L, H, dtype=self.dtype, device=self.device)
        attn = torch.zeros(B, L, dtype=torch.long, device=self.device)
        lbl = torch.full((B, L), -100, dtype=torch.long, device=self.device)
        for i, (s, la) in enumerate(zip(seqs, labs)):
            n = s.shape[0]
            inp[i, :n] = s; attn[i, :n] = 1; lbl[i, :n] = la
        return {"inputs_embeds": inp, "attention_mask": attn, "labels": lbl}

    def forward(self, packs, messages_list, answers):
        batch = self.training_batch(packs, messages_list, answers)
        return self.model(**batch)

    # ---- inference ----
    @torch.no_grad()
    def generate(self, pack, messages, max_new_tokens=512):
        pid = _apply_template(self.tok, messages)[0].to(self.device)
        wm = self._wm_embed(pack)
        inp = torch.cat([wm, self._text_embed(pid)], 0)[None]          # [1,k+t,H]
        attn = torch.ones(inp.shape[:2], dtype=torch.long, device=self.device)
        out = self.model.generate(inputs_embeds=inp, attention_mask=attn,
                                  max_new_tokens=max_new_tokens, do_sample=False,
                                  pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id)
        return self.tok.decode(out[0], skip_special_tokens=True).strip()

    def save_trainables(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        torch.save(self.projector.state_dict(), Path(path) / "projector.pt")
        if self.use_lora:
            self.model.save_pretrained(str(Path(path) / "lora_adapter"))

    def load_trainables(self, path):
        sd = torch.load(Path(path) / "projector.pt", map_location=self.device)
        self.projector.load_state_dict(sd)
        if self.use_lora and (Path(path) / "lora_adapter").exists():
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, str(Path(path) / "lora_adapter"))
