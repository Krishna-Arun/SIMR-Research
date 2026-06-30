"""Thin OpenAI-compatible client for a locally-served vLLM model (agent-under-test or judge).
Real PHI stays local — never points at a hosted API.

Two tool-calling paths:
  * native  — vLLM tool parser surfaces .tool_calls (Qwen=hermes, Llama=llama3_json, gpt-oss=openai).
  * manual  — for models with NO vLLM tool parser (gemma-3). We force schema-constrained JSON via
              guided decoding ({reasoning, tool, arguments}), rewrite tool/assistant turns into plain
              text the base chat template accepts, and synthesize a ToolCall. The benchmark agent
              loops (run_eval_a/b/c) are unchanged — they still see .tool_calls.
Manual mode auto-engages when the model id contains 'gemma' (override with manual_tools=).
"""
from __future__ import annotations
import json, os
from dataclasses import dataclass, field
from openai import OpenAI


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Chat:
    text: str
    tool_calls: list = field(default_factory=list)


def _tool_catalog(tools):
    lines = ["You can use exactly ONE tool per turn. Available tools:"]
    for t in tools:
        f = t["function"]
        params = f.get("parameters", {}).get("properties", {})
        req = f.get("parameters", {}).get("required", [])
        ps = ", ".join(f"{k}{'*' if k in req else ''}: {v.get('type','any')}"
                       + (f" (enum {v['enum']})" if 'enum' in v else "")
                       + (f" [items {v['items'].get('properties',{})}]" if v.get('type')=='array' and isinstance(v.get('items'),dict) else "")
                       for k, v in params.items()) or "(no args)"
        lines.append(f"- {f['name']}: {f.get('description','')}  args: {ps}")
    lines.append('Respond with ONLY a JSON object: {"reasoning": "...", "tool": "<name>", '
                 '"arguments": {<the tool\'s args>}}. Fill every required (*) arg. No prose outside the JSON.')
    return "\n".join(lines)


def _manual_messages(messages, tools):
    """Rewrite native tool/assistant-tool_calls turns into plain text + inject the tool catalog."""
    out = []
    cat_done = False
    for m in messages:
        role = m.get("role")
        if role == "system":
            out.append({"role": "system", "content": (m.get("content") or "") + "\n\n" + _tool_catalog(tools)})
            cat_done = True
        elif role == "assistant" and m.get("tool_calls"):
            tc = m["tool_calls"][0]["function"]
            out.append({"role": "assistant",
                        "content": json.dumps({"tool": tc["name"], "arguments": json.loads(tc["arguments"] or "{}")})})
        elif role == "tool":
            out.append({"role": "user", "content": "TOOL RESULT: " + (m.get("content") or "")})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    if not cat_done:
        out.insert(0, {"role": "system", "content": _tool_catalog(tools)})
    return out


_MANUAL_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "tool": {"type": "string"},
        "arguments": {"type": "object"},
    },
    "required": ["tool", "arguments"],
}


class LLM:
    def __init__(self, model_id: str, endpoint: str = "http://localhost:8000/v1",
                 temperature: float = 0.2, max_tokens: int = 4096,
                 reasoning_effort: str | None = None, manual_tools: bool | None = None):
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        # manual guided-JSON tool-calling: forced for gemma (no vLLM parser), or via EVAL_FORCE_MANUAL=1
        # (used for Llama after its native llama3_json path crashed the engine).
        if manual_tools is None:
            self.manual = ("gemma" in model_id.lower()) or os.environ.get("EVAL_FORCE_MANUAL") == "1"
        else:
            self.manual = manual_tools
        self.client = OpenAI(base_url=endpoint, api_key="EMPTY", timeout=600)
        self._n = 0

    def chat(self, messages, tools=None, temperature=None) -> Chat:
        temp = self.temperature if temperature is None else temperature
        # ── manual (guided-JSON) tool-calling for parserless models ──
        if self.manual and tools:
            names = [t["function"]["name"] for t in tools]
            schema = dict(_MANUAL_SCHEMA)
            schema["properties"] = dict(_MANUAL_SCHEMA["properties"], tool={"type": "string", "enum": names})
            kw = dict(model=self.model_id, messages=_manual_messages(messages, tools),
                      temperature=temp, max_tokens=self.max_tokens,
                      extra_body={"guided_json": schema})
            content = self.client.chat.completions.create(**kw).choices[0].message.content or ""
            try:
                obj = json.loads(content)
                name = obj.get("tool")
                if name not in names:
                    return Chat(text=content, tool_calls=[])
                self._n += 1
                return Chat(text=obj.get("reasoning", "") or "",
                            tool_calls=[ToolCall(f"call_{self._n}", name, obj.get("arguments") or {})])
            except (json.JSONDecodeError, AttributeError):
                return Chat(text=content, tool_calls=[])
        # ── native tool-calling ──
        kw = dict(model=self.model_id, messages=messages, temperature=temp, max_tokens=self.max_tokens)
        if self.reasoning_effort:
            kw["extra_body"] = {"reasoning_effort": self.reasoning_effort}
        if tools:
            kw["tools"] = tools
            kw["tool_choice"] = "auto"
        m = self.client.chat.completions.create(**kw).choices[0].message
        calls = []
        for tc in (getattr(m, "tool_calls", None) or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(tc.id, tc.function.name, args))
        return Chat(text=m.content or "", tool_calls=calls)
