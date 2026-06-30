"""Model-agnostic agentic tool-calling driver.

Runs a local vLLM model in a tool-use loop against the PubMed MCP server. Two protocols:
  * react (default): the model emits ONE JSON action per turn —
        {"action":"tool","tool":"search_articles","args":{...}}   or   {"action":"final","result":{...}}
    Robust to DeepSeek-R1's verbose <think> preambles (we strip them and take the last balanced JSON).
  * native: uses vLLM/OpenAI function-calling (message.tool_calls).

Enforces a per-invocation tool-call budget and a circuit breaker (via ToolDispatcher). The `result`
of the final action is returned to the caller (optimizer/evaluator) for schema validation.
"""
from __future__ import annotations

import json
import re

from qgen.tools import ToolDispatcher, catalog_text, to_openai_tools
from qgen.vllm_backend import ChatResult, VLLMChat

try:
    import json_repair                       # tolerant parser for LLM JSON (truncated / unescaped)
except Exception:                            # pragma: no cover
    json_repair = None

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _loads(frag: str):
    """Parse one JSON fragment: strict first, then tolerant repair (handles truncation/bad quotes)."""
    for attempt in (frag, frag.replace("'", '"').replace("\n", " ")):
        try:
            return json.loads(attempt)
        except Exception:
            pass
    if json_repair is not None:
        try:
            obj = json_repair.loads(frag)
            if obj not in (None, "", {}, []):
                return obj
        except Exception:
            pass
    return None


def _balanced_objects(text: str) -> list[str]:
    """All top-level balanced {...} substrings."""
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
    # last resort: output had no balanced object (e.g. truncated) -> repair the whole thing
    if json_repair is not None and '"action"' in clean:
        obj = _loads(clean[clean.index("{"):]) if "{" in clean else None
        if isinstance(obj, dict) and obj.get("action") in ("tool", "final"):
            return obj
    return None


REACT_SYSTEM = """You are a meticulous clinical research assistant with access to PubMed tools.
On EACH turn reply with EXACTLY ONE JSON object and nothing else:
  to search literature:  {{"action":"tool","tool":"<tool_name>","args":{{...}}}}
  when done:             {{"action":"final","result":{{...}}}}
Available tools:
{catalog}
Rules:
- Query PubMed with GENERAL clinical concepts only (e.g. "lactate sepsis mortality guideline").
- NEVER put patient identifiers, dates, or raw lab values in a tool query.
- Use at most {budget} tool calls, then emit your final answer.
- Your "result" MUST match the JSON schema described in the user message."""


def run_agentic(llm: VLLMChat, dispatcher: ToolDispatcher, mcp_tools: list[dict],
                task_messages: list[dict], budget: int, forbidden_ids: list[str] | None = None,
                max_unparseable: int = 2) -> dict | None:
    """Drive the tool-use loop; return the final action's `result` dict (or None on failure)."""
    if llm.native_tools:
        return _run_native(llm, dispatcher, mcp_tools, task_messages, budget, forbidden_ids)

    sys_msg = {"role": "system",
               "content": REACT_SYSTEM.format(catalog=catalog_text(mcp_tools), budget=budget)}
    messages = [sys_msg] + task_messages
    calls = 0
    unparseable = 0
    while True:
        res: ChatResult = llm.chat(messages, tools=None)
        messages.append({"role": "assistant", "content": res.text})
        action = parse_action(res.text)
        if action is None:
            unparseable += 1
            if unparseable > max_unparseable:
                return None
            messages.append({"role": "user",
                             "content": "Reply with ONE JSON object: an {\"action\":\"tool\",...} "
                                        "or {\"action\":\"final\",\"result\":{...}}."})
            continue
        unparseable = 0
        if action["action"] == "final":
            return action.get("result")
        # tool action
        if calls >= budget or dispatcher.tripped:
            messages.append({"role": "user",
                             "content": "Tool budget reached or PubMed unavailable. "
                                        "Emit {\"action\":\"final\",\"result\":{...}} now."})
            continue
        obs = dispatcher.dispatch(action.get("tool", ""), action.get("args", {}) or {}, forbidden_ids)
        calls += 1
        messages.append({"role": "user", "content": f"OBSERVATION ({calls}/{budget}):\n{obs}"})


def _run_native(llm, dispatcher, mcp_tools, task_messages, budget, forbidden_ids):
    tools = to_openai_tools(mcp_tools)
    messages = list(task_messages)
    calls = 0
    while True:
        res: ChatResult = llm.chat(messages, tools=tools)
        if res.tool_calls and calls < budget and not dispatcher.tripped:
            messages.append({"role": "assistant", "content": res.text or None,
                             "tool_calls": [{"id": tc.id, "type": "function",
                                             "function": {"name": tc.name, "arguments": json.dumps(tc.args)}}
                                            for tc in res.tool_calls]})
            for tc in res.tool_calls:
                obs = dispatcher.dispatch(tc.name, tc.args, forbidden_ids)
                calls += 1
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})
            continue
        action = parse_action(res.text) or {}
        return action.get("result") if action.get("action") == "final" else _loose_json(res.text)


def _loose_json(text: str) -> dict | None:
    for frag in reversed(_balanced_objects(_THINK.sub(" ", text))):
        obj = _loads(frag)
        if obj is not None:
            return obj
    return None
