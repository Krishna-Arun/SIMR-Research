export const meta = {
  name: 'dirchange-one-each-seq',
  description: 'One dirchange case per reversal type, sequential',
}

const MANIFEST_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange/output/cardiac_dirchange_benchmark_v1.json'
const CASES_DIR     = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange/output/cardiac-dirchange'

const PREDICTION_SCHEMA = {
  type: 'object', required: ['predicted_value','predicted_unit','direction','confidence','reasoning'],
  properties: { predicted_value:{type:'number'}, predicted_unit:{type:'string'}, direction:{type:'string',enum:['rising','falling','stable']}, confidence:{type:'string',enum:['high','medium','low']}, reasoning:{type:'string'} },
}

const CASES_SCHEMA = { type:'object', required:['cases'], properties: { cases:{type:'array'} } }

phase('One per reversal type')

// Load manifest (just the lightweight one)
const manifest = await agent(`Read JSON at ${MANIFEST_PATH}, return full object with cases array.`, { label:'load-manifest', phase:'One per reversal type', schema:CASES_SCHEMA })
if (!manifest || !manifest.cases.length) throw new Error('No manifest')

// One case per reversal type
const selection = manifest.cases.filter(c => [1, 4, 3, 8].includes(Number(c.case_id))).map(c => Number(c.case_id))

let results = []
for (const id of selection) {
  const entry = manifest.cases.find(c => Number(c.case_id) === id)
  if (!entry) continue

  log(`Processing case ${id}...`)

  // Load full case via StructuredOutput (clean JSON parse, no text round-trip)
  const paddedId = String(entry.case_id).padStart(3,'0')
  const caseFile = entry.file || `${CASES_DIR}/case_${paddedId}.json`
  const caseData = await agent(`Read the JSON file at ${caseFile}. Return the full parsed object.`, { label:`load-${id}`, phase:'One per reversal type', schema:{type:'object'} })
  if (!caseData) continue

  // Build prompt — use key summaries, not raw thousands-of-rows dumps
  const trops = (caseData.trop_context || []).map(t => `  ${t.datetime}: ${t.value} ng/mL`).join('\n') || '  None'

  // Only include unique gap-lab categories + counts, not every row
  const gapLabs = caseData.gap_labs || []
  const gapCounts = {}
  gapLabs.forEach(g => { const lbl = g?.label; if(lbl) gapCounts[lbl] = (gapCounts[lbl]||0)+1 })
  const gapSummary = Object.entries(gapCounts).map(([lbl,n]) => `  ${lbl}: ${n} measurements`).join('\n') || '  None'

  // Unique diagnoses by code (deduped, first 20)
  const diagMap = new Map()
  (caseData.diagnoses||[]).forEach(d => { const c=d?.code; if(c && !diagMap.has(c)) diagMap.set(c, d.description) })
  const diagLines = [...diagMap.entries()].slice(0,20).map(([c,d]) => `  ${c}: ${d}`).join('\n') || '  None'

  // Unique meds by name (deduped, first 15)
  const medNames = [...new Set((caseData.medications||[]).map(m=>m?.name))].slice(0,15)
  const medLines = medNames.length ? medNames.map(n => `  ${n}`).join('\n') : '  None'

  // Recent procedures (first 10)
  const procLines = (caseData.procedures||[]).slice(0,10).map(p=>`  ${p.date}: ${p.description||p.code}`).join('\n') || '  None'

  // First 20 lab timeline entries (just the head — covers early labs)
  const labHead = (caseData.lab_timeline||[]).slice(0,20).map(l=>`| ${l.datetime} | ${l.label} | ${l.value} | ${l.unit} |`).join('\n') || '  None'

  const prompt = `You are an expert cardiologist and intensivist. Predict the NEXT Troponin I value for this patient.

══════ PATIENT ══
${caseData.question.stem}

══════ DIAGNOSIS CODES (unique, first 20) ══
${diagLines}

══════ MEDICATIONS (unique, first 15) ══
${medLines}

══════ PROCEDURES (first 10) ══
${procLines}

══════ TROPONIN I HISTORY ══
${trops}

══════ GAP-LAB CATEGORIES (between last troponin and target) ══
${gapSummary}

══════ LAB TIMELINE (first 20 of ${caseData.lab_timeline?.length||0}) ══
| Datetime | Lab | Value | Unit |
|---|---|---|---|
${labHead}

══════ PREDICTION TASK ══
Predict Troponin I at: ${caseData.question.target_datetime} (${caseData.question.hours_ahead}h after last known)
Visible trend: ${caseData.question.visible_trend}

Clinical context: STEMI peaks 12-24h then falls; NSTEMI rises slower. ≥20% delta in 3h = AMI. Renal impairment → chronic elevation. Use cross-lab signals to detect the reversal.

Call StructuredOutput with your prediction.`

  const prediction = await agent(prompt, { label:`predict-${id}`, phase:'One per reversal type', schema:PREDICTION_SCHEMA })

  // Score using manifest entry's ground truth (no need to load it again)
  const gtValue = entry.actual_value
  const gtDir = entry.actual_dir
  const predicted = prediction?.predicted_value || 0
  const actual = typeof gtValue === 'number' ? gtValue : 0
  const dirMatch = prediction?.direction === gtDir
  const relError = actual > 0 ? Math.abs(predicted - actual)/actual : 1.0
  const within50 = relError<=0.50, within20 = relError<=0.20
  let score=0; if(dirMatch)score+=0.40; if(within50)score+=0.35; if(within20)score+=0.25

  results.push({
    case_id: entry.case_id, patient_id: entry.patient_id, reversal_type: caseData.reversal_type, vis_trend: caseData.vis_trend,
    predicted_value: predicted, predicted_dir: prediction?.direction || 'unknown', actual_value: actual, actual_dir: gtDir,
    confidence: prediction?.confidence || 'N/A', direction_correct: dirMatch, rel_error_pct: Math.round(relError*100),
    within_50pct: within50, within_20pct: within20, score: Math.round(score*100)/100,
  })

  log(`  case ${id} (${caseData.reversal_type}): pred=${prediction?.direction||'?'} actual=${gtDir} score=${Math.round(score*100)/100}`)
}

const meanScore = results.length ? Math.round(results.reduce((s,r)=>s+r.score,0)/results.length*1000)/1000 : 0
log(`Mean: ${meanScore}, Cases: ${results.length}/4`)
return { per_type: results, overall_mean_score: meanScore }
