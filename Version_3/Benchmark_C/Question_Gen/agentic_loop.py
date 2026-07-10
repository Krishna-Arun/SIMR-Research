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
