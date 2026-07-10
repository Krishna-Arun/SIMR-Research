import json, yaml, sys
from qgen.config import load_config
from qgen.context_builder import ContextStore
from qgen.mcp_client import MCPClient
from qgen.tools import ToolDispatcher
from qgen.optimizer import OptimizerAgent, render_context, DRAFT_INSTRUCTIONS
from qgen.hf_backend import make_chat
from qgen.schema import CANDIDATE_TEMPLATE, is_valid_candidate
from qgen.agentic_loop import parse_action

cfg = load_config("config/qgen_pilot.yaml")
mcp = MCPClient(cfg).start()
disp = ToolDispatcher(cfg, mcp)
store = ContextStore(cfg)
opt_llm = make_chat(cfg["models"]["optimizer"])
print("optimizer loaded:", opt_llm.model_id, "device", opt_llm.device, flush=True)

hadm = list(store.pool)[0]
ctx = store.build_context(hadm)
prompt = render_context(ctx) + "\n\n" + DRAFT_INSTRUCTIONS.format(qtype="diagnosis", template=json.dumps(CANDIDATE_TEMPLATE, indent=2))

# 1) RAW single-shot output (no agentic loop) to see Llama's format + length
raw = opt_llm.chat([{"role":"user","content":prompt}], temperature=0.3)
print("\n=========== RAW LLAMA OUTPUT (len chars=%d) ===========" % len(raw.text), flush=True)
print(raw.text[:2600], flush=True)
print("\n=========== parse_action on raw ===========", flush=True)
act = parse_action(raw.text)
print("parsed action:", None if act is None else {k:(v if k!='result' else '<<result dict keys: %s>>'%list(v.keys()) if isinstance(v,dict) else type(v).__name__) for k,v in act.items()}, flush=True)

# 2) full agentic draft as the orchestrator does it
opt = OptimizerAgent(opt_llm, disp, mcp.tools, int(cfg["generation"]["max_tool_calls_per_agent"]))
cand = opt.draft(ctx, "diagnosis")
print("\n=========== draft() result ===========", flush=True)
print("type:", type(cand).__name__, "| is_valid:", is_valid_candidate(cand), flush=True)
if isinstance(cand, dict):
    print("keys:", list(cand.keys()), flush=True)
    print("question_text:", str(cand.get('question_text'))[:200], flush=True)
    print("type field:", cand.get('type'), "| gold_labs is list:", isinstance(cand.get('gold_labs'), list), flush=True)
mcp.close()
