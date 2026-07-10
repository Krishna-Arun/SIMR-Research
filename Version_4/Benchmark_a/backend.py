"""
Shared local-LLM backend for the question-generation agents.

Two interchangeable backends behind one `LocalLLM.chat()` interface:
  * ollama  (default locally) — talks to a running Ollama server on localhost:11434
    via its /api/chat endpoint. No torch needed. Real PHI stays on the device.
  * hf                        — loads a Hugging Face causal LM from
    ../../loaded_models/<key> (or the hub). For the GPU cluster.

Pick with env var SIMR_BACKEND=ollama|hf (default: ollama). Each agent
instantiates a LocalLLM with its own model key; the key maps to an Ollama tag
(OLLAMA_TAGS) or an HF snapshot (models.yaml).
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

LOADED_MODELS = Path(__file__).resolve().parents[2] / "loaded_models"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

DEFAULT_BACKEND = os.environ.get("SIMR_BACKEND", "ollama")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# models.yaml key -> Ollama tag
OLLAMA_TAGS = {
    "mistral-small-3.1": "mistral-small3.1",
    "phi-4-mini": "phi4-mini",
    "gpt-oss-20b": "gpt-oss:20b",
    # convenience fallbacks
    "qwen3-8b": "qwen3:8b",
    "llama-3.1-8b": "llama3.1:8b",
    "gemma-4-e4b": "gemma3n:e4b",
}


def _resolve_hf_source(model_key: str) -> str:
    import yaml
    with open(LOADED_MODELS / "models.yaml") as f:
        registry = {e["key"]: e for e in yaml.safe_load(f)["models"]}
    if model_key not in registry:
        raise KeyError(f"Unknown model key '{model_key}'. Options: {', '.join(registry)}")
    local = LOADED_MODELS / model_key
    if local.exists() and any(local.iterdir()):
        return str(local)
    return registry[model_key]["repo_id"]


class LocalLLM:
    """Chat wrapper that speaks to Ollama (default) or a local HF model."""

    def __init__(self, model_key: str, load_in_4bit: bool = False, backend: str | None = None):
        self.model_key = model_key
        self.load_in_4bit = load_in_4bit
        self.backend = backend or DEFAULT_BACKEND
        self._tok = None
        self._model = None

    # ── Ollama ────────────────────────────────────────────────────────────
    def _ollama_tag(self) -> str:
        return OLLAMA_TAGS.get(self.model_key, self.model_key)

    def _ollama_chat(self, messages, max_new_tokens, temperature) -> str:
        payload = {
            "model": self._ollama_tag(),
            "messages": messages,
            "stream": False,
            "options": {"temperature": float(temperature), "num_predict": int(max_new_tokens),
                        "num_ctx": int(os.environ.get("SIMR_NUM_CTX", "16384"))},
        }
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = json.loads(r.read().decode())
        return (resp.get("message", {}) or {}).get("content", "").strip()

    # ── Hugging Face ──────────────────────────────────────────────────────
    def _ensure_hf(self):
        if self._model is not None:
            return
        import torch
        from dotenv import load_dotenv
        from transformers import AutoModelForCausalLM, AutoTokenizer
        load_dotenv(ENV_FILE)
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        src = _resolve_hf_source(self.model_key)
        kwargs = dict(torch_dtype=torch.bfloat16, device_map="auto", token=token)
        if self.load_in_4bit:
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
        self._tok = AutoTokenizer.from_pretrained(src, token=token)
        self._model = AutoModelForCausalLM.from_pretrained(src, **kwargs)

    def _hf_chat(self, messages, max_new_tokens, temperature) -> str:
        self._ensure_hf()
        input_ids = self._tok.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt").to(self._model.device)
        out = self._model.generate(
            input_ids, max_new_tokens=max_new_tokens,
            do_sample=temperature > 0, temperature=max(temperature, 1e-5))
        return self._tok.decode(out[0][input_ids.shape[-1]:], skip_special_tokens=True).strip()

    def chat_tools(self, messages: list[dict], tools: list[dict],
                   max_new_tokens: int = 1500, temperature: float = 0.3) -> dict:
        """Ollama native tool-calling. Returns the assistant message dict
        ({content, tool_calls?}). Pass tools=None/[] for a plain final turn."""
        payload = {
            "model": self._ollama_tag(), "messages": messages, "stream": False,
            "options": {"temperature": float(temperature), "num_predict": int(max_new_tokens),
                        "num_ctx": int(os.environ.get("SIMR_NUM_CTX", "16384"))},
        }
        if tools:
            payload["tools"] = tools
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            resp = json.loads(r.read().decode())
        return resp.get("message", {}) or {}

    # ── public ────────────────────────────────────────────────────────────
    def chat(self, messages: list[dict], max_new_tokens: int = 1024,
             temperature: float = 0.7) -> str:
        if self.backend == "ollama":
            return self._ollama_chat(messages, max_new_tokens, temperature)
        return self._hf_chat(messages, max_new_tokens, temperature)
