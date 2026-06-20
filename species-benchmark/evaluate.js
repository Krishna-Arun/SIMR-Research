export const meta = {
  name: 'species-benchmark-eval',
  description: 'Evaluate AI clinical reasoning across dog/horse/fictional-species lab cases',
  phases: [
    { title: 'Load',     detail: 'Read benchmark cases from species_benchmark_v1.json' },
    { title: 'Answer',   detail: 'Agent answers each case given full lab panel' },
    { title: 'Grade',    detail: 'Score each response: correct_action, pivot_cited, threshold_used' },
    { title: 'Report',   detail: 'Aggregate results by tier and action type' },
  ],
}

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/species-benchmark/output/species_benchmark_v1.json'

// ── args: { case_ids?, tiers?, max_cases? } ───────────────────────────────────
const _tiers     = (args && args.tiers)     ? args.tiers     : [1, 2, 3]
const _max_cases = (args && args.max_cases) ? Number(args.max_cases) : 15

// ── Schemas ───────────────────────────────────────────────────────────────────

const ANSWER_SCHEMA = {
  type: 'object',
  required: ['recommended_action', 'pivot_labs', 'reasoning'],
  properties: {
    recommended_action: { type: 'string',  description: 'The single most appropriate next clinical action' },
    pivot_labs: {
      type: 'array',
      items: { type: 'string' },
      description: 'Lab names that most drove the decision',
    },
    reasoning: { type: 'string', description: '3-5 sentence clinical rationale citing lab values vs provided reference ranges' },
  },
}

const GRADE_SCHEMA = {
  type: 'object',
  required: ['correct_action', 'pivot_lab_cited', 'threshold_compared', 'total', 'explanation'],
  properties: {
    correct_action:    { type: 'number', description: '1.0 if action matches; 0.0 if not' },
    pivot_lab_cited:   { type: 'number', description: '1.0 if pivot lab name appears in reasoning; 0.0 if not' },
    threshold_compared:{ type: 'number', description: '1.0 if reasoning explicitly compares pivot value to the provided species reference range; 0.0 if only general knowledge used' },
    total:             { type: 'number', description: 'Mean of the three components' },
    explanation:       { type: 'string', description: 'Brief grader explanation of each score' },
  },
}

const LOAD_SCHEMA = {
  type: 'object',
  required: ['cases'],
  properties: {
    cases: {
      type: 'array',
      items: {
        type: 'object',
        required: ['case_id', 'species', 'tier', 'action_label', 'question_stem', 'rubric'],
        properties: {
          case_id:       { type: 'number' },
          species:       { type: 'string' },
          tier:          { type: 'number' },
          action_label:  { type: 'string' },
          question_stem: { type: 'string' },
          rubric: {
            type: 'object',
            required: ['correct_action_readable', 'correct_synonyms', 'pivot_lab', 'pivot_value', 'pivot_threshold', 'pivot_unit', 'pivot_direction'],
          },
        },
      },
    },
  },
}

// ── Phase 0: Load ─────────────────────────────────────────────────────────────
phase('Load')
log('Reading species_benchmark_v1.json ...')

const loaded = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}.
Return the top-level "cases" array. Each case has: case_id, species, tier, n_labs, action_label, question_stem, rubric (with correct_action_readable, correct_synonyms, pivot_lab, pivot_value, pivot_threshold, pivot_unit, pivot_direction).
Filter to cases where tier is one of: ${JSON.stringify(_tiers)}.
Return at most ${_max_cases} cases, prioritising tier 3 (Velox noctis) first, then tier 2, then tier 1.`,
  { label: 'benchmark-loader', phase: 'Load', schema: LOAD_SCHEMA }
)

if (!loaded || !loaded.cases || loaded.cases.length === 0) {
  throw new Error('Failed to load benchmark cases')
}

const cases = loaded.cases
log(`Loaded ${cases.length} cases (tiers: ${[...new Set(cases.map(c=>c.tier))].join(', ')})`)

// ── Phase 1: Answer + Grade (pipeline) ───────────────────────────────────────
phase('Answer')

const results = await pipeline(
  cases,

  // Stage 1: Agent answers the case
  async (c) => {
    const prompt = `You are a clinical expert. A patient of species "${c.species}" has presented with the following laboratory panel. All species-specific reference ranges are provided in the question. You MUST use ONLY the provided reference ranges — not your training knowledge of human or other species ranges.

${c.question_stem}`

    const answer = await agent(prompt, {
      label:  `answer:case${c.case_id}:${c.species}`,
      phase:  'Answer',
      schema: ANSWER_SCHEMA,
    })

    if (!answer) return null
    return { case: c, answer }
  },

  // Stage 2: Grade the response
  async (result, original) => {
    if (!result) return null
    const { case: c, answer } = result

    const rubric = c.rubric
    const synonyms_str = rubric.correct_synonyms.join('", "')

    const grade_prompt = `You are grading a clinical AI response. Score these 3 binary criteria.

CASE: Species=${c.species} (Tier ${c.tier}), Action=${c.action_label}

RUBRIC:
- correct_action: The correct answer is "${rubric.correct_action_readable}". Accepted synonyms: "${synonyms_str}". Score 1.0 if the recommended_action matches any synonym (case-insensitive, substring match OK). Score 0.0 if completely wrong.
- pivot_lab_cited: The key lab driving the decision is "${rubric.pivot_lab}" (value: ${rubric.pivot_value} ${rubric.pivot_unit}, threshold: ${rubric.pivot_direction} ${rubric.pivot_threshold} ${rubric.pivot_unit}). Score 1.0 if the reasoning mentions "${rubric.pivot_lab}" by name. Score 0.0 if it's not mentioned.
- threshold_compared: Score 1.0 if the reasoning explicitly compares ${rubric.pivot_value} to the provided species reference range (ref: see case). Score 0.0 if the agent used only general clinical knowledge without citing the provided range.

AGENT RESPONSE:
Recommended action: ${answer.recommended_action}
Pivot labs cited: ${answer.pivot_labs.join(', ')}
Reasoning: ${answer.reasoning}

Grade all three criteria. total = mean(correct_action, pivot_lab_cited, threshold_compared).`

    const grade = await agent(grade_prompt, {
      label:  `grade:case${c.case_id}:${c.species}`,
      phase:  'Grade',
      schema: GRADE_SCHEMA,
    })

    if (!grade) return null
    log(`Case ${c.case_id} [${c.species} T${c.tier}] ${c.action_label}: total=${grade.total.toFixed(2)} | action=${grade.correct_action} pivot=${grade.pivot_lab_cited} threshold=${grade.threshold_compared}`)

    return {
      case_id:            c.case_id,
      species:            c.species,
      tier:               c.tier,
      action_label:       c.action_label,
      n_labs:             c.n_labs,
      recommended_action: answer.recommended_action,
      correct_action:     grade.correct_action,
      pivot_lab_cited:    grade.pivot_lab_cited,
      threshold_compared: grade.threshold_compared,
      total:              grade.total,
      explanation:        grade.explanation,
    }
  }
)

// ── Phase 2: Report ───────────────────────────────────────────────────────────
phase('Report')

const valid = results.filter(Boolean)
log(`Graded ${valid.length}/${cases.length} cases successfully`)

// Aggregate by tier
const byTier = {}
for (const r of valid) {
  if (!byTier[r.tier]) byTier[r.tier] = []
  byTier[r.tier].push(r)
}

const tierNames = { 1: 'Dog (T1)', 2: 'Horse (T2)', 3: 'Velox noctis T3)' }
const avg = arr => arr.length ? (arr.reduce((a,b)=>a+b,0)/arr.length).toFixed(3) : 'n/a'

log('')
log('╔══════════════════════════════════════════════════════════════════╗')
log('║  SPECIES-INVARIANT CLINICAL REASONING BENCHMARK — RESULTS       ║')
log('╠══════════════════════════════════════════════════════════════════╣')
log('║  Tier        | n  | correct_action | pivot_cited | threshold | total')
log('║  ------------|----|---------  -----|-----------  |-----------|------')

for (const [tier, rows] of Object.entries(byTier).sort()) {
  const name    = tierNames[tier] || `Tier ${tier}`
  const correct  = avg(rows.map(r=>r.correct_action))
  const pivot    = avg(rows.map(r=>r.pivot_lab_cited))
  const thresh   = avg(rows.map(r=>r.threshold_compared))
  const total    = avg(rows.map(r=>r.total))
  log(`║  ${name.padEnd(12)} | ${String(rows.length).padStart(2)} | ${correct.padEnd(14)} | ${pivot.padEnd(11)} | ${thresh.padEnd(9)} | ${total}`)
}

log('╠══════════════════════════════════════════════════════════════════╣')
const allCorrect  = avg(valid.map(r=>r.correct_action))
const allPivot    = avg(valid.map(r=>r.pivot_lab_cited))
const allThresh   = avg(valid.map(r=>r.threshold_compared))
const allTotal    = avg(valid.map(r=>r.total))
log(`║  OVERALL      | ${String(valid.length).padStart(2)} | ${allCorrect.padEnd(14)} | ${allPivot.padEnd(11)} | ${allThresh.padEnd(9)} | ${allTotal}`)
log('╚══════════════════════════════════════════════════════════════════╝')

// Breakdown by action
log('')
log('Results by action type:')
const byAction = {}
for (const r of valid) {
  if (!byAction[r.action_label]) byAction[r.action_label] = []
  byAction[r.action_label].push(r)
}
for (const [action, rows] of Object.entries(byAction)) {
  const t = avg(rows.map(r=>r.total))
  log(`  ${action.padEnd(35)}: ${t} (n=${rows.length})`)
}

return {
  n_cases:   valid.length,
  by_tier:   Object.fromEntries(Object.entries(byTier).map(([k,v]) => [k, {
    n:              v.length,
    correct_action: parseFloat(avg(v.map(r=>r.correct_action))),
    pivot_cited:    parseFloat(avg(v.map(r=>r.pivot_lab_cited))),
    threshold:      parseFloat(avg(v.map(r=>r.threshold_compared))),
    total:          parseFloat(avg(v.map(r=>r.total))),
  }])),
  overall: {
    correct_action: parseFloat(allCorrect),
    pivot_cited:    parseFloat(allPivot),
    threshold:      parseFloat(allThresh),
    total:          parseFloat(allTotal),
  },
  detailed_results: valid,
}
