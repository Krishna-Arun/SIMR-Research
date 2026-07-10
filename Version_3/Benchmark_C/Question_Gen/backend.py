"""
Shared local-LLM backend for the Benchmark A question-generation agents.

Wraps a Hugging Face causal LM (one of the models downloaded into
Version_3/loaded_models/) behind a tiny `chat()` interface. Each agent
(optimizer / evaluator / scorer) instantiates a LocalLLM with its own model key.

INFRA ONLY — meant to run on a GPU node, not the laptop.
"""
from __future__ import annotations

import os
from pathlib import Path

import torch
import yaml
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer

# Version_3/loaded_models holds the weights + registry.
LOADED_MODELS = Path(__file__).resolve().parents[2] / "loaded_models"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _resolve_source(model_key: str) -> str:
    """Map a models.yaml key to a local snapshot dir, or fall back to the hub repo_id."""
    with open(LOADED_MODELS / "models.yaml") as f:
        registry = {e["key"]: e for e in yaml.safe_load(f)["models"]}
    if model_key not in registry:
        raise KeyError(f"Unknown model key '{model_key}'. Options: {', '.join(registry)}")
    local = LOADED_MODELS / model_key
    if local.exists() and any(local.iterdir()):
        return str(local)
    return registry[model_key]["repo_id"]


class LocalLLM:
    """Lazily-loaded chat wrapper around one HF causal LM."""

    def __init__(self, model_key: str, load_in_4bit: bool = False):
        self.model_key = model_key
        self.load_in_4bit = load_in_4bit
        self._tok = None
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        load_dotenv(ENV_FILE)
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        src = _resolve_source(self.model_key)
        kwargs = dict(torch_dtype=torch.bfloat16, device_map="auto", token=token)
        if self.load_in_4bit:
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16
            )
        self._tok = AutoTokenizer.from_pretrained(src, token=token)
        self._model = AutoModelForCausalLM.from_pretrained(src, **kwargs)

    def chat(self, messages: list[dict], max_new_tokens: int = 1024,
             temperature: float = 0.7) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}, ...] -> reply text."""
        self._ensure_loaded()
        input_ids = self._tok.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to(self._model.device)
        out = self._model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0,
            temperature=max(temperature, 1e-5),
        )
        return self._tok.decode(out[0][input_ids.shape[-1]:], skip_special_tokens=True).strip()
