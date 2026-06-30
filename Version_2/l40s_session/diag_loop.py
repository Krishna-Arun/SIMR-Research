import json
from qgen.config import load_config
from qgen.context_builder import ContextStore
from qgen.mcp_client import MCPClient
from qgen.tools import ToolDispatcher, catalog_text
from qgen.optimizer import render_context, DRAFT_INSTRUCTIONS
from qgen.hf_backend import make_chat
from qgen.schema import CANDIDATE_TEMPLATE
from qgen.agentic_loop import parse_action, REACT_SYSTEM

cfg = load_config("config/qgen_pilot.yaml")
mcp = MCPClient(cfg).start()
disp = ToolDispatcher(cfg, mcp)
store = ContextStore(cfg)
llm = make_chat(cfg["models"]["optimizer"])
budget = int(cfg["generation"]["max_tool_calls_per_agent"])
ctx = store.build_context(list(store.pool)[0])
prompt = render_context(ctx) + "\n\n" + DRAFT_INSTRUCTIONS.format(qtype="diagnosis", template=json.dumps(CANDIDATE_TEMPLATE, indent=2))

sys_msg = {"role":"system","content":REACT_SYSTEM.format(catalog=catalog_text(mcp.tools), budget=budget)}
messages=[sys_msg, {"role":"user","content":prompt}]
calls=0; unparseable=0
for turn in range(1, 8):
    res = llm.chat(messages, tools=None)
    messages.append({"role":"assistant","content":res.text})
    act = parse_action(res.text)
    print(f"\n--- TURN {turn}: output len={len(res.text)} parsed={'None' if act is None else act.get('action')} ---", flush=True)
    print("OUTPUT HEAD:", repr(res.text[:300]), flush=True)
    print("OUTPUT TAIL:", repr(res.text[-200:]), flush=True)
    if act is None:
        unparseable+=1
        print("  >> UNPARSEABLE", unparseable, flush=True)
        if unparseable>2: print(">>> RETURN None (too many unparseable)"); break
        messages.append({"role":"user","content":"Reply with ONE JSON object."}); continue
    unparseable=0
    if act["action"]=="final":
        r=act.get("result"); print(">>> FINAL result type:", type(r).__name__, "keys:", list(r.keys()) if isinstance(r,dict) else r); break
    if calls>=budget or disp.tripped:
        messages.append({"role":"user","content":"Budget reached. Emit final now."}); print("  budget reached, asking final"); continue
    obs=disp.dispatch(act.get("tool",""), act.get("args",{}) or {})
    calls+=1
    print(f"  TOOL {act.get('tool')} -> obs len {len(obs)}", flush=True)
    messages.append({"role":"user","content":f"OBSERVATION ({calls}/{budget}):\n{obs}"})
mcp.close()
