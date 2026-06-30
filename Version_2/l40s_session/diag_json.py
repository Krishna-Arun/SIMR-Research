import json
from qgen.config import load_config
from qgen.context_builder import ContextStore
from qgen.mcp_client import MCPClient
from qgen.tools import ToolDispatcher, catalog_text
from qgen.optimizer import render_context, DRAFT_INSTRUCTIONS
from qgen.hf_backend import make_chat
from qgen.schema import CANDIDATE_TEMPLATE, is_valid_candidate
from qgen.agentic_loop import parse_action, REACT_SYSTEM, _balanced_objects
import json_repair

cfg = load_config("config/qgen_pilot.yaml")
mcp = MCPClient(cfg).start(); disp = ToolDispatcher(cfg, mcp); store = ContextStore(cfg)
llm = make_chat(cfg["models"]["optimizer"]); budget=int(cfg["generation"]["max_tool_calls_per_agent"])
ctx = store.build_context(list(store.pool)[0])
prompt = render_context(ctx)+"\n\n"+DRAFT_INSTRUCTIONS.format(qtype="diagnosis", template=json.dumps(CANDIDATE_TEMPLATE, indent=2))
msgs=[{"role":"system","content":REACT_SYSTEM.format(catalog=catalog_text(mcp.tools),budget=budget)},{"role":"user","content":prompt}]
calls=0
for t in range(6):
    res=llm.chat(msgs,tools=None); msgs.append({"role":"assistant","content":res.text})
    act=parse_action(res.text)
    if act and act["action"]=="tool" and calls<budget:
        obs=disp.dispatch(act.get("tool",""),act.get("args",{}) or {}); calls+=1
        msgs.append({"role":"user","content":f"OBSERVATION:\n{obs}"}); continue
    # this is the final turn (parse_action gave None or final)
    frag=_balanced_objects(res.text)[0] if _balanced_objects(res.text) else res.text
    print("FINAL frag len:", len(frag))
    try:
        json.loads(frag); print("stdlib json.loads: OK")
    except Exception as e:
        print("stdlib json.loads ERROR:", e)
        pos=getattr(e,'pos',None)
        if pos: print("  around error:", repr(frag[max(0,pos-60):pos+60]))
    rep=json_repair.loads(frag)
    print("json_repair -> dict?", isinstance(rep,dict), "valid_candidate?", is_valid_candidate(rep))
    break
mcp.close()
