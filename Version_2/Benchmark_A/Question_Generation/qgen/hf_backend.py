"""In-process HuggingFace-transformers backend (fallback for when vLLM won't run on el7/V100).

Same interface as qgen.vllm_backend.VLLMChat (.chat / .healthy / .native_tools) so the agentic loop
and orchestrator don't care which backend is used. Uses 4-bit quantization (bitsandbytes) so small
models fit a 16 GB V100, and a module-level weight cache so two roles sharing a model_id load it once.

Concurrency: each HFChat owns a lock so a single model is never entered by two threads at once
(HF `generate` is not safe for that). Two DIFFERENT models (e.g. optimizer on cuda:0, evaluator on
cuda:1) run truly in parallel — pin them with role_cfg['cuda_device'].

Mirrors the proven loading pattern in
Version_1/CARDIAC_COUNTERFACTUAL/models/llm_inference.py (HuggingFaceLLMPredictor).
"""
from __future__ import annotations

import threading

from qgen.vllm_backend import ChatResult

_MODEL_CACHE: dict = {}   # (model_id, cuda_device) -> (tokenizer, model)
_CACHE_LOCK = threading.Lock()


def _load(model_id: str, load_4bit: bool, max_memory_per_gpu: str | None = None,
          cuda_device: str | None = None):
    key = (model_id, cuda_device)
    with _CACHE_LOCK:
        if key in _MODEL_CACHE:
            return _MODEL_CACHE[key]
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    kwargs = {"trust_remote_code": True}
    if load_4bit:
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
        kwargs["device_map"] = "auto"
    else:
        kwargs["dtype"] = torch.float16
        if cuda_device:
            # pin the whole model to ONE gpu so it can run concurrently with the other role
            kwargs["device_map"] = {"": cuda_device}
        else:
            kwargs["device_map"] = "auto"
            if max_memory_per_gpu and torch.cuda.is_available():
                n = torch.cuda.device_count()
                kwargs["max_memory"] = {i: max_memory_per_gpu for i in range(n)}
                kwargs["max_memory"]["cpu"] = "0GiB"   # forbid CPU offload (keep it all on GPU)
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    model.eval()
    with _CACHE_LOCK:
        _MODEL_CACHE[key] = (tok, model)
    return tok, model


class HFChat:
    native_tools = False

    def __init__(self, role_cfg: dict):
        self.model_id = role_cfg["model_id"]
        self.temperature = float(role_cfg.get("temperature", 0.2))
        self.max_tokens = int(role_cfg.get("max_tokens", 2048))
        self.load_4bit = bool(role_cfg.get("load_4bit", True))
        self.cuda_device = role_cfg.get("cuda_device")
        self.tok, self.model = _load(self.model_id, self.load_4bit,
                                     role_cfg.get('max_memory_per_gpu'), self.cuda_device)
        # serialize generate() for THIS model; different models hold different locks -> run in parallel
        self._lock = threading.Lock()
        # where to place inputs: the pinned device, or the first param's device for an auto-split model
        self.device = self.cuda_device or next(self.model.parameters()).device

    def healthy(self) -> bool:
        return self.model is not None

    def chat(self, messages: list[dict], tools=None, temperature: float | None = None) -> ChatResult:
        import torch
        # native tool messages aren't used in the react path; keep only role/content
        msgs = [{"role": m["role"], "content": m.get("content") or ""} for m in messages
                if m.get("role") in ("system", "user", "assistant")]
        enc = self.tok.apply_chat_template(msgs, add_generation_prompt=True,
                                           return_tensors="pt", return_dict=True)
        enc = {k: v.to(self.device) for k, v in enc.items()}
        temp = self.temperature if temperature is None else temperature
        gen_kwargs = dict(max_new_tokens=self.max_tokens, pad_token_id=self.tok.eos_token_id)
        if temp and temp > 0:
            gen_kwargs.update(do_sample=True, temperature=temp)
        else:
            gen_kwargs.update(do_sample=False)
        with self._lock:                       # one thread per model at a time
            with torch.no_grad():
                out = self.model.generate(**enc, **gen_kwargs)
        input_len = enc["input_ids"].shape[1]
        text = self.tok.decode(out[0][input_len:], skip_special_tokens=True)
        return ChatResult(text=text)


def make_chat(role_cfg: dict):
    """Factory: pick backend by role_cfg['backend'] (vllm | hf). Default vllm."""
    backend = role_cfg.get("backend", "vllm")
    if backend == "hf":
        return HFChat(role_cfg)
    from qgen.vllm_backend import VLLMChat
    return VLLMChat(role_cfg)
