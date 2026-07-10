"""
Agentic tool-calling driver (ReAct-JSON) for the local generation models.

The local HF models have no native function-calling API, so we drive a simple
ReAct loop: each turn the model emits exactly ONE JSON action —
  {"action":"tool","tool":"search_articles","args":{...}}   or
  {"action":"final","result":{...}}
We dispatch tool actions through the PubMed ToolDispatcher, feed the observation
back, and return the final action's `result` to the caller.

Robust to verbose/reasoning preambles: we strip <think>...</think> and take the
last balanced JSON object. Enforces a tool-call budget + a circuit breaker.
Adapted from the Version_2 qgen agentic loop; backend swapped to LocalLLM.
"""
from __future__ import annotations

import json
import re

from tools import ToolDispatcher, catalog_text

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _loads(frag: str):
    for attempt in (frag, frag.replace("'", '"').replace("\n", " ")):
        try:
            return json.loads(attempt)
        except Exception:
            pass
    return None


def _balanced_objects(text: str) -> list[str]:
    objs, i, n = [], 0, len(text)
    while i < n:
        if text[i] == "{":
            depth = 0
            for e in range(i, n):
                if text[e] == "{":
                    depth += 1
                elif text[e] == "}":
                    depth -= 1
                    if depth == 0:
                        objs.append(text[i:e + 1]); i = e + 1; break
            else:
                break
        else:
            i += 1
    return objs


def extract_json_obj(text: str) -> dict | None:
    """Last top-level balanced {...} object in text, tolerant of prose/<think>."""
    clean = _THINK.sub(" ", text or "")
    best, depth, start = None, 0, 0
    for i, ch in enumerate(clean):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                frag = clean[start:i + 1]
                obj = _loads(frag)
                if isinstance(obj, dict):
                    best = obj
    return best


def to_ollama_tools(mcp_tools: list[dict], allow: set | None = None) -> list[dict]:
    """Convert MCP tool defs into Ollama/OpenAI function-tool schemas."""
    out = []
    for t in mcp_tools:
        if allow is not None and t["name"] not in allow:
            continue
        out.append({"type": "function", "function": {
            "name": t["name"], "description": (t.get("description") or "")[:500],
            "parameters": t.get("inputSchema", {"type": "object", "properties": {}})}})
    return out


def run_agentic_native(llm, dispatcher, mcp_tools, messages, budget: int = 10,
                       allow: set | None = None, max_new_tokens: int = 1500,
                       final_key: str = "stem", max_nudges: int = 4) -> dict | None:
    """Native Ollama tool-calling loop. The model calls tools until it stops; its
    final message content is parsed as the result JSON. If it narrates without a
    tool call and without a complete final object, we NUDGE it to continue (call a
    tool or emit ONLY the final JSON). Returns the result dict or None.

    `final_key`: a key that must be present for the JSON to count as the final
    answer (guards against returning an intermediate/partial object)."""
    tools = to_ollama_tools(mcp_tools, allow)
    msgs = list(messages)
    calls = nudges = 0
    while True:
        # once the model stops calling tools (starts narrating), compel a JSON-only
        # turn by disabling tools — mirrors the behavior that reliably yields the final.
        force_final = calls >= budget or dispatcher.tripped or nudges > 0
        m = llm.chat_tools(msgs, None if force_final else tools, max_new_tokens=max_new_tokens)
        tcs = m.get("tool_calls") or []
        content = m.get("content", "") or ""

        if tcs and not force_final:
            msgs.append({"role": "assistant", "content": content, "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function", {}) or {}
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = _loads(args) or {}
                obs = dispatcher.dispatch(name, args)
                calls += 1
                msgs.append({"role": "tool", "content": str(obs)[:2000], "tool_name": name})
            continue

        obj = extract_json_obj(content)
        if isinstance(obj, dict) and final_key in obj:
            return obj                                     # complete final answer
        # narration / partial: nudge for a JSON-only turn (tools are now off via force_final)
        nudges += 1
        if nudges > max_nudges:
            return obj                                     # best effort after the nudge cap
        msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content":
                     "Do NOT narrate and do NOT refuse. Using whatever data you have already "
                     "retrieved, output ONLY the final JSON object now — start with { and end "
                     f"with }} — and it MUST include \"{final_key}\", \"options\", \"correct_options\"."})


def parse_action(text: str) -> dict | None:
    """Extract the last valid {"action": ...} object from model output."""
    clean = _THINK.sub(" ", text)
    for frag in reversed(_balanced_objects(clean)):
        obj = _loads(frag)
        if isinstance(obj, dict) and obj.get("action") in ("tool", "final"):
            return obj
    return None


REACT_SYSTEM = """You have access to PubMed tools. On EACH turn reply with EXACTLY
ONE JSON object and nothing else:
  to search literature:  {{"action":"tool","tool":"<tool_name>","args":{{...}}}}
  when done:             {{"action":"final","result":{{...}}}}
Available tools:
{catalog}
Rules:
- Query PubMed with GENERAL clinical concepts only (e.g. "lactate sepsis mortality guideline").
- NEVER put patient identifiers, dates, or raw lab values in a tool query.
- Use at most {budget} tool calls, then emit your final answer.
- Your "result" MUST match the JSON structure the user asks for."""


def run_agentic(llm, dispatcher: ToolDispatcher, mcp_tools: list[dict],
                task_messages: list[dict], budget: int = 4,
                max_unparseable: int = 2, max_new_tokens: int = 1024) -> dict | None:
    """Drive the ReAct loop; return the final action's `result` dict (or None on failure).

    llm: a backend.LocalLLM (or anything with .chat(messages, ...) -> str).
    """
    sys_msg = {"role": "system",
               "content": REACT_SYSTEM.format(catalog=catalog_text(mcp_tools), budget=budget)}
    messages = [sys_msg] + list(task_messages)
    calls = unparseable = 0
    while True:
        text = llm.chat(messages, max_new_tokens=max_new_tokens, temperature=0.3)
        messages.append({"role": "assistant", "content": text})
        action = parse_action(text)
        if action is None:
            unparseable += 1
            if unparseable > max_unparseable:
                return None
            messages.append({"role": "user",
                             "content": 'Reply with ONE JSON object: {"action":"tool",...} '
                                        'or {"action":"final","result":{...}}.'})
            continue
        unparseable = 0
        if action["action"] == "final":
            return action.get("result")
        if calls >= budget or dispatcher.tripped:
            messages.append({"role": "user",
                             "content": 'Tool budget reached or PubMed unavailable. '
                                        'Emit {"action":"final","result":{...}} now.'})
            continue
        obs = dispatcher.dispatch(action.get("tool", ""), action.get("args", {}) or {})
        calls += 1
        messages.append({"role": "user", "content": f"OBSERVATION ({calls}/{budget}):\n{obs}"})
