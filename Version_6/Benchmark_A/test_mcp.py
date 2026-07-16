import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

def txt(res):
    return json.loads(res.content[0].text)

async def main():
    idx = json.load(open(os.path.join(HERE, "index", "cases_index.json")))
    cid = next(c for c, e in idx.items() if e["cohort"] == "dialysis")
    e = idx[cid]
    params = StdioServerParameters(command=PY, args=[os.path.join(HERE, "mcp_server.py")],
                                   env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])

            cat = txt(await s.call_tool("request_all_supplementals_no_values", {"case_id": cid}))
            c = cat["catalog"]
            print(f"\ncatalog for {cid}: {len(c['labs'])} labs, {len(c['medications'])} meds, "
                  f"{len(c['coronary_contrast'])} contrast")
            print("  first 5 lab names:", [l["name"] for l in c["labs"][:5]])
            print("  sample lab entry (NO values):", c["labs"][0])

            one = txt(await s.call_tool("request_a_supplemental",
                      {"case_id": cid, "name": "Creatinine",
                       "causal_justification": "assessing renal function trend"}))
            print(f"\nrequest Creatinine -> {one.get('type')}, "
                  f"{len(one.get('data',[]))} values; first: "
                  f"{one['data'][0] if one.get('data') else None}")
            print("  justification echoed:", one.get("causal_justification"))

            gp = txt(await s.call_tool("get_patient_data",
                     {"subject_id": e["subject_id"], "hadm_id": e["hadm_id"]}))
            gt = gp.get("ground_truth", {})
            print(f"\nget_patient_data ground truth: intervention={gt['intervention']['type']}, "
                  f"{len(gt['icd_codes'])} icd codes; primary dx: "
                  f"{gt['icd_codes'][0]['icd']} = {gt['icd_codes'][0]['title'][:50]}")

            bad = txt(await s.call_tool("request_a_supplemental",
                      {"case_id": cid, "name": "Troponarble",
                       "causal_justification": "x"}))
            print("\nunknown-name handling:", "error" in bad, "(available_labs listed:",
                  "available_labs" in bad, ")")
    print("\nMCP server OK.")

asyncio.run(main())
