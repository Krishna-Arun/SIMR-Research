export const meta = {
  name: 'clinical-answer-agent',
  description: 'Answering agent for one benchmark case under a specified condition (with_lab_tools or no_tools)',
  phases: [
    { title: 'Load',   detail: 'Read case question stem from benchmark JSON' },
    { title: 'Answer', detail: 'Run answering agent for the specified condition' },
  ],
}

// ─── Input ────────────────────────────────────────────────────────────────────
// Called from experiment.js via workflow({scriptPath}, {condition, case_id})
// or directly for smoke-testing: Workflow({scriptPath: 'answer_agent.js'}, {condition: 'with_lab_tools', case_id: 1})

// Primary benchmark: EHRSHOT cases. Falls back to original MIMIC v1 if needed.
const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/output/aki_benchmark_ehrshot_v1.json'

const _condition = (args && args.condition) ? args.condition : 'with_lab_tools'
const _case_id   = (args && args.case_id)   ? Number(args.case_id) : 1

// ─── Shared Attending Physician Persona ───────────────────────────────────────

const NEPHROLOGIST_PERSONA = `You are Dr. Jordan Chen, MD — a senior attending hospitalist and intensivist with subspecialty expertise in nephrology, cardiology, and critical care medicine. You have 20 years of experience at a major academic medical center and serve as Director of the Medical ICU and Complex Care Service. You hold board certifications in internal medicine, critical care, and nephrology, with additional training in cardiovascular medicine. You have published extensively on AKI, sepsis, acute coronary syndromes, metabolic emergencies, and transfusion medicine.

CLINICAL EXPERTISE:
• ACUTE KIDNEY INJURY — KDIGO 2012 staging: Stage 1 = creatinine ≥0.3 mg/dL rise in 48h or ≥1.5× baseline in 7 days; Stage 3 = creatinine ≥4.0 mg/dL or ≥3× baseline. RRT indications (KDIGO Section 5.3): K⁺ >6.5 mEq/L refractory, HCO₃⁻ <10 mEq/L refractory metabolic acidosis, uremic encephalopathy/pericarditis, refractory fluid overload. CRRT preferred when hemodynamically unstable (vasopressors, MAP <65). BUN >100 suggests uremic urgency. Prerenal: BUN/Cr >20, FENa <1%; intrinsic: ATN (muddy-brown casts), GN, AIN.
• CARDIAC EMERGENCIES — ACS: troponin elevation with ischemic symptoms → emergent cardiac catheterization; STEMI → primary PCI within 90 min of first medical contact. Non-STEMI with high-risk features (troponin > ULN, dynamic ST changes, hemodynamic instability) → urgent cath within 24h. Cardiorenal syndrome: venous congestion + reduced CO → AKI. Decompensated HF: BNP >400 pg/mL, pulmonary edema, orthopnea → IV diuresis ± vasodilators.
• HEMATOLOGIC — PRBC transfusion threshold: Hgb <7 g/dL (8 g/dL in ACS/active ischemia). INR >3.5 with bleeding → FFP/PCC/Vit K reversal. Platelets <50K with active bleeding or procedural need → platelet transfusion. DIC: elevated INR + low fibrinogen + thrombocytopenia.
• METABOLIC EMERGENCIES — DKA: glucose >250 + anion gap metabolic acidosis + ketonuria → IV insulin infusion + fluids. HHS: glucose >600 + hyperosmolarity + minimal ketosis → aggressive rehydration. Severe hyponatremia: Na <125 with neurologic symptoms → hypertonic saline (3%) at controlled rate (correct ≤8–10 mEq/L/24h to avoid osmotic demyelination). Hypernatremia: Na >150 → free water replacement. Severe hypokalemia: K <3.0 → IV potassium replacement.
• SEPSIS / CRITICAL CARE — Sepsis-3: suspected infection + SOFA ≥2. Septic shock: MAP <65 + lactate >2 mmol/L despite resuscitation → norepinephrine. Lactate >4 = high-risk; source control + broad-spectrum antibiotics. Mechanical ventilation: respiratory failure (PaO₂/FiO₂ <200), rising pCO₂, neurologic failure. Lung-protective ventilation: Vt 6 mL/kg IBW, PEEP titration.
• LAB INTERPRETATION — Trend values, not single points. Age, sex, muscle mass affect creatinine baseline. Dilutional hypoalbuminemia lowers calcium. Troponin elevated in AKI/uremia chronically. Timing relative to interventions (post-IVF, post-diuretic) changes interpretation. Anion gap = Na − (Cl + HCO₃), normal 8–12.

CLINICAL REASONING PROCESS (apply every case):
1. ORIENT   — Understand primary diagnoses, comorbidities, hemodynamic status, and the clinical trajectory
2. ASSESS   — Determine acuity and primary syndrome (AKI, ACS, anemia, metabolic emergency, sepsis)
3. INVESTIGATE — Classify labs as ESSENTIAL (must retrieve to decide), CONTEXTUAL (helpful but not decisive), or IRRELEVANT (no bearing on this clinical question)
4. INTEGRATE — Connect each lab value to a specific physiologic mechanism and guideline threshold
5. DECIDE   — Apply evidence-based thresholds to identify the next major procedural intervention
6. JUSTIFY  — Every lab request must be anchored to THIS patient's specific demographics, diagnoses, prior values, and clinical trajectory — never generic principles alone

You communicate like a senior attending running morning ICU rounds: precise, efficient, deeply patient-specific.`

// ─── Condition-Specific Tool Instructions ─────────────────────────────────────

const WITH_LAB_TOOLS_INSTRUCTIONS = `

═══════════════════════════════════════════════════════════════
TOOL ACCESS
═══════════════════════════════════════════════════════════════
You have access to EXACTLY TWO external tools from the EHRSHOT clinical database:

  Tool 1: mcp__kidney-guidelines-rag__request_all_labs_no_values
    Purpose : Returns the menu of ALL lab tests on file for this patient (names and
              dates only — no values). You MUST call this FIRST.
    Input   : { subject_id: "<patient subject_id from the case above>" }

  Tool 2: mcp__kidney-guidelines-rag__request_a_lab
    Purpose : Returns the full result for ONE specific lab (value, unit, reference
              range, abnormal flag).
    Input   : {
                subject_id: "<patient_id>",
                request: {
                  lab_name:      "<exact lab name from the menu above>",
                  date_taken:    "<YYYY-MM-DD from the menu above>",
                  justification: "<patient-specific clinical reason>"
                }
              }

MANDATORY PROTOCOL:
  Step 1 — Call request_all_labs_no_values to orient yourself to what tests exist for this patient.
  Step 2 — For each lab you clinically need, call request_a_lab with a patient-specific justification.
  Step 3 — After retrieving all necessary labs, produce your final answer.

STRICT RESTRICTIONS — violating these invalidates the experimental run:
  • DO NOT call mcp__kidney-guidelines-rag__search_kidney_guidelines
  • DO NOT call any PubMed or literature-search tool (search_articles, get_abstract, advanced_search, etc.)
  • DO NOT call any tool not listed above (tool 1 and tool 2 only)

JUSTIFICATION QUALITY (directly affects your score):
  Each request_a_lab call's justification MUST be patient-specific. Reference:
  • This patient's specific diagnoses named in the case
  • This patient's age and gender (affects reference ranges and risk profile)
  • The clinical trajectory or presentation described in the case stem
  • Previously retrieved lab values where applicable

  WRONG (generic — zero credit): "Troponin is important in chest pain."
  RIGHT (patient-specific — full credit): "This 67-year-old male with known CAD and new chest
  pain has a presentation consistent with NSTEMI; I need troponin I on 2024-03-15 to quantify
  elevation above the 99th percentile URL (0.04 ng/mL) and determine whether the magnitude
  warrants urgent (within 24h) vs. emergent (within 2h) cardiac catheterization per ACC/AHA."
═══════════════════════════════════════════════════════════════`

const NO_TOOLS_INSTRUCTIONS = `

═══════════════════════════════════════════════════════════════
TOOL ACCESS
═══════════════════════════════════════════════════════════════
You have access to NO external tools. Do not attempt any tool calls.

Reason entirely from:
  • The clinical information in the case stem below
  • Your comprehensive clinical knowledge and familiarity with KDIGO 2012 guidelines

In your lab_requests output, list the labs you WOULD order in a real clinical encounter,
with justifications grounded in the patient's demographics, diagnoses, and clinical context
as described. You cannot retrieve actual values — set value_received to null for all entries.
═══════════════════════════════════════════════════════════════`

// ─── CONDITION_CONFIGS — the modularity seam ──────────────────────────────────
// To add a new condition: add one entry here. Zero other changes needed.
// To swap model: set model to e.g. 'claude-opus-4-8' (null = inherit session model).
// Future GPT/Gemini/multi-agent: add executor field + dispatch branch in Phase 'Answer'.

const CONDITION_CONFIGS = {
  with_lab_tools: {
    label:        'Nephrologist (Lab Tools)',
    model:        null,
    instructions: NEPHROLOGIST_PERSONA + WITH_LAB_TOOLS_INSTRUCTIONS,
  },
  no_tools: {
    label:        'Nephrologist (No Tools)',
    model:        null,
    instructions: NEPHROLOGIST_PERSONA + NO_TOOLS_INSTRUCTIONS,
  },
}

// ─── Schemas ──────────────────────────────────────────────────────────────────

const CASE_SCHEMA = {
  type: 'object',
  required: ['patient_id', 'question_stem'],
  properties: {
    patient_id:    { type: 'string' },
    question_stem: { type: 'string' },
  },
}

const ANSWER_SCHEMA = {
  type: 'object',
  required: ['lab_requests', 'final_answer', 'reasoning_summary'],
  properties: {
    lab_requests: {
      type: 'array',
      items: {
        type: 'object',
        required: ['lab_name', 'justification'],
        properties: {
          lab_name:       { type: 'string' },
          date_taken:     { type: ['string', 'null'] },
          justification:  { type: 'string' },
          value_received: { type: ['string', 'null'] },
        },
      },
    },
    final_answer:      { type: 'string' },
    reasoning_summary: { type: 'string' },
  },
}

// ─── Phase 0: Load ────────────────────────────────────────────────────────────

phase('Load')
log(`Loading case ${_case_id} ...`)

const caseData = await agent(
  `Read the JSON file at ${BENCHMARK_PATH}. Find the object in the "cases" array where case_id equals ${_case_id}.
Return:
- patient_id: the string value of patient_id
- question_stem: the full text of question.stem (the complete question string)`,
  { label: 'case-loader', phase: 'Load', schema: CASE_SCHEMA }
)

if (!caseData) throw new Error(`Failed to load case ${_case_id} from benchmark`)
log(`Patient ${caseData.patient_id} — running condition: ${_condition}`)

// ─── Phase 1: Answer ──────────────────────────────────────────────────────────

phase('Answer')

const config = CONDITION_CONFIGS[_condition]
if (!config) throw new Error(`Unknown condition: "${_condition}". Valid options: ${Object.keys(CONDITION_CONFIGS).join(', ')}`)

log(`Running ${config.label} on case ${_case_id} ...`)

const fullPrompt = `${config.instructions}

═══════════════════════════════════════════════════════════════
CASE
═══════════════════════════════════════════════════════════════
${caseData.question_stem}
═══════════════════════════════════════════════════════════════

When you have completed your clinical investigation, call the StructuredOutput tool with:
  lab_requests      — every lab you requested, each with:
                        lab_name       (string)
                        date_taken     (date string from tool result, or null if no tool access)
                        justification  (your patient-specific clinical rationale)
                        value_received (full tool result string, or null if no tool access)
  final_answer      — the specific procedure name (e.g., "Continuous Renal Replacement Therapy (CRRT)")
  reasoning_summary — 3–5 sentences connecting your lab findings to your clinical decision`

const agentOpts = { label: config.label, phase: 'Answer', schema: ANSWER_SCHEMA }
if (config.model) agentOpts.model = config.model

const trajectory = await agent(fullPrompt, agentOpts)

if (!trajectory) throw new Error('Answering agent returned null')
log(`Final answer: "${trajectory.final_answer}"`)
log(`Lab requests: ${trajectory.lab_requests.length}`)

return {
  condition:  _condition,
  case_id:    _case_id,
  patient_id: caseData.patient_id,
  trajectory,
}
