"""Thin client for a local vLLM OpenAI-compatible endpoint (one per model role).

Real PHI is involved, so models run LOCALLY only — this never points at a hosted API. Returns a
small ChatResult so the agentic loop is backend-agnostic. Includes a health check the orchestrator
polls before starting (waits for the vLLM server to come up).
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


class VLLMChat:
    def __init__(self, role_cfg: dict):
        self.model_id = role_cfg["model_id"]
        self.endpoint = role_cfg["endpoint"]
        self.temperature = float(role_cfg.get("temperature", 0.2))
        self.max_tokens = int(role_cfg.get("max_tokens", 2048))
        self.native_tools = role_cfg.get("tool_calling", "react") == "native"
        self.reasoning_effort = role_cfg.get("reasoning_effort")   # gpt-oss: low|medium|high
        self.client = OpenAI(base_url=self.endpoint, api_key="EMPTY", timeout=600)

    def healthy(self) -> bool:
        try:
            self.client.models.list()
            return True
        except Exception:
            return False

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float | None = None) -> ChatResult:
        kwargs = dict(model=self.model_id, messages=messages,
                      temperature=self.temperature if temperature is None else temperature,
                      max_tokens=self.max_tokens)
        if self.reasoning_effort:
            kwargs["extra_body"] = {"reasoning_effort": self.reasoning_effort}
        if tools and self.native_tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
        return ChatResult(text=msg.content or "", tool_calls=calls)
