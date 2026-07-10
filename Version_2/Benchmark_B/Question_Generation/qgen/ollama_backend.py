"""Ollama backend for local model serving via OpenAI-compatible API.

Ollama runs locally on macOS/Linux (M1+, GPU, or CPU) and exposes models via
OpenAI-compatible /v1 endpoint. Both optimizer and evaluator connect to the same
Ollama instance (different models, sequential or parallel via OS scheduling).

Real PHI stays local — Ollama never leaves the device.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from openai import OpenAI


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class OllamaChat:
    """Client for Ollama local models via OpenAI-compatible API."""

    native_tools = False  # Ollama doesn't support native tool_calls; use ReAct

    def __init__(self, role_cfg: dict):
        self.model_id = role_cfg["model_id"]  # e.g. "qwen3.6:latest", "deepseek-r1:14b"
        self.endpoint = role_cfg.get("endpoint", "http://localhost:11434/v1")
        self.temperature = float(role_cfg.get("temperature", 0.2))
        self.max_tokens = int(role_cfg.get("max_tokens", 2048))
        # Ollama: apiKey can be anything (it's local); timeout generous for long generations
        self.client = OpenAI(base_url=self.endpoint, api_key="ollama", timeout=600)

    def healthy(self) -> bool:
        """Check if Ollama endpoint is reachable and model is loaded."""
        try:
            models = self.client.models.list()
            # Check if our target model is available
            model_names = [m.id for m in models.data]
            return any(self.model_id in name or name in self.model_id for name in model_names)
        except Exception as e:
            print(f"Ollama health check failed: {e}")
            return False

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        """
        Call Ollama model. Tools are ignored (Ollama doesn't support native tool_calls);
        the agentic loop handles ReAct parsing instead.
        """
        temp = self.temperature if temperature is None else temperature
        kwargs = dict(
            model=self.model_id,
            messages=messages,
            temperature=temp,
            max_tokens=self.max_tokens,
        )
        # Note: tools param is ignored; ReAct loop in agentic_loop.py handles tool parsing from text

        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        # Ollama via OpenAI doesn't return tool_calls; they're embedded in text for ReAct
        return ChatResult(text=msg.content or "", tool_calls=[])
