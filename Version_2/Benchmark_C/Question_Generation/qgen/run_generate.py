"""Entrypoint: wire MCP + vLLM endpoints + agents and generate questions.

Usage:
  python -m qgen.run_generate [config.yaml] [--target N] [--pilot]

Requires the two vLLM servers to be up (serve_models.sbatch) and reachable at the endpoints in
qgen.yaml. Polls /v1/models until both are healthy, then runs the orchestrator. Resumable.
"""
from __future__ import annotations

import argparse
import sys
import time

from qgen.config import load_config, out_dir
from qgen.context_builder import ContextStore
from qgen.evaluator import EvaluatorAgent
from qgen.mcp_client import MCPClient
from qgen.optimizer import OptimizerAgent
from qgen.orchestrator import Orchestrator
from qgen.hf_backend import make_chat
from qgen.tools import ToolDispatcher
from qgen.writer import Writer


def wait_healthy(llm: VLLMChat, name: str, timeout_s: int = 1800):
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if llm.healthy():
            print(f"  {name} endpoint healthy: {getattr(llm, 'endpoint', 'in-process')} ({llm.model_id})")
            return True
        time.sleep(10)
    raise RuntimeError(f"{name} endpoint not healthy within {timeout_s}s: {getattr(llm, 'endpoint', 'in-process')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", nargs="?", default=None)
    ap.add_argument("--target", type=int, default=None)
    ap.add_argument("--pilot", action="store_true", help="generate a small pilot batch (default 20)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    gen = cfg["generation"]
    budget = int(gen["max_tool_calls_per_agent"])

    target = args.target or (20 if args.pilot else int(gen["target_n"]))

    print("[1] starting PubMed MCP server ...")
    mcp = MCPClient(cfg).start()
    print("    tools:", [t["name"] for t in mcp.tools][:6], "...")
    dispatcher = ToolDispatcher(cfg, mcp)

    print("[2] connecting model backends ...")
    opt_llm = make_chat(cfg["models"]["optimizer"])
    eval_llm = make_chat(cfg["models"]["evaluator"])
    wait_healthy(opt_llm, "optimizer")
    wait_healthy(eval_llm, "evaluator")

    print("[3] building cohort store + agents ...")
    store = ContextStore(cfg)
    optimizer = OptimizerAgent(opt_llm, dispatcher, mcp.tools, budget)
    evaluator = EvaluatorAgent(eval_llm, dispatcher, mcp.tools, budget)
    writer = Writer(out_dir(cfg))
    orch = Orchestrator(cfg, store, optimizer, evaluator, dispatcher, writer)

    print(f"[4] generating up to {target} questions (resume from {writer.count()}) ...")
    n, counts = orch.generate(target, float(gen["diagnosis_frac"]), int(cfg["seed"]))
    print(f"DONE: {n} questions  {counts}")
    mcp.close()
    return 0 if n >= target else 1


if __name__ == "__main__":
    sys.exit(main())
