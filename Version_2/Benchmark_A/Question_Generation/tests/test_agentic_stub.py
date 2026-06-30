"""End-to-end test of the agentic tool path WITHOUT a real model.

A StubLLM scripts ReAct turns (a PubMed tool call, then a final answer). Validates
agentic_loop -> tools -> mcp_client -> sanitizer against the LIVE PubMed MCP server. This exercises
everything except the (still-to-be-chosen) vLLM models.

Run:  PYTHONPATH=. python tests/test_agentic_stub.py
"""
from __future__ import annotations

from qgen.agentic_loop import run_agentic
from qgen.config import load_config
from qgen.mcp_client import MCPClient
from qgen.tools import ToolDispatcher
from qgen.vllm_backend import ChatResult


class StubLLM:
    """Mimics VLLMChat: scripted ReAct outputs; records observations it receives."""
    native_tools = False

    def __init__(self, script):
        self.script = list(script)
        self.turn = 0
        self.seen_observations = []

    def chat(self, messages, tools=None, temperature=None):
        for m in messages:
            if m["role"] == "user" and str(m["content"]).startswith("OBSERVATION"):
                self.seen_observations.append(m["content"])
        out = self.script[min(self.turn, len(self.script) - 1)]
        self.turn += 1
        return ChatResult(text=out)


def main():
    cfg = load_config()
    mcp = MCPClient(cfg).start()
    dispatcher = ToolDispatcher(cfg, mcp)

    script = [
        '{"action":"tool","tool":"search_articles","args":{"query":"vancomycin MRSA bacteremia guideline","max_results":3}}',
        '{"action":"final","result":{"question_text":"stub","type":"diagnosis","gold_labs":[],"gold_micro":[],'
        '"reference_answer":"stub","causal_chain":["a -> b -> c"],"pubmed_citations":[]}}',
    ]
    llm = StubLLM(script)
    result = run_agentic(llm, dispatcher, mcp.tools,
                         [{"role": "user", "content": "Generate a stub question."}],
                         budget=4, forbidden_ids=["10000032", "22595853"])

    assert result is not None, "agentic loop returned None"
    assert result["type"] == "diagnosis", result
    assert llm.seen_observations, "no PubMed observation was fed back to the model"
    obs = llm.seen_observations[0]
    assert "pmid" in obs.lower() or "articles" in obs.lower(), f"observation looks wrong: {obs[:200]}"
    print("PASS: agentic tool path works end-to-end")
    print("  final result keys:", list(result.keys()))
    print("  first observation (trimmed):", obs[:160].replace("\n", " "))

    # PHI gate: a tool call carrying an identifier must be blocked (counted as TOOL_ERROR, not crash)
    bad = dispatcher.dispatch("search_articles", {"query": "patient 22595853 sepsis"},
                              forbidden_ids=["22595853"])
    assert bad.startswith("TOOL_ERROR"), bad
    print("PASS: PHI gate blocks identifier in query")
    mcp.close()


if __name__ == "__main__":
    main()
