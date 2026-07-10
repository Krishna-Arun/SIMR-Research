export const meta = {
  name: 'test-pubmed',
  description: 'Test: confirm mcp__pubmed-server__search_articles is callable from a workflow subagent',
  phases: [{ title: 'Test', detail: 'Single agent calls PubMed and reports result' }],
}

const SCHEMA = {
  type: 'object',
  required: ['tool_called', 'result_snippet', 'num_results'],
  properties: {
    tool_called:    { type: 'boolean', description: 'Did you successfully call mcp__pubmed-server__search_articles?' },
    result_snippet: { type: 'string',  description: 'First 300 chars of the PubMed response, or "FAILED: <error>" if it did not work.' },
    num_results:    { type: 'number',  description: 'Number of articles returned, or 0 if failed.' },
  },
}

phase('Test')

const result = await agent(
  `You are a tool-availability test agent. Your only job is to call one tool and report what happened.

STEP 1: Call mcp__pubmed-server__search_articles RIGHT NOW with these exact parameters:
  query: "KDIGO acute kidney injury renal replacement therapy indications 2012"
  max_results: 3

STEP 2: Return structured output:
  tool_called = true if the call succeeded, false if it failed or the tool was not available
  result_snippet = first 300 chars of what the tool returned, or "FAILED: <reason>" if it did not work
  num_results = how many articles came back (0 if failed)

Do not use any other tools. Do not search the web. Just call mcp__pubmed-server__search_articles and report back.`,
  { label: 'pubmed-test', phase: 'Test', schema: SCHEMA }
)

log(`PubMed called: ${result.tool_called}  |  results: ${result.num_results}`)
log(`Snippet: ${result.result_snippet.slice(0, 150)}`)

return result
