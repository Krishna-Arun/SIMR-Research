export const meta = {
  name: 'aki-answer-agent',
  description: 'Answering agent for one AKI benchmark case under a specified condition (with_lab_tools or no_tools)',
  phases: [
    { title: 'Load',   detail: 'Read case question stem from aki_benchmark_v1.json' },
    { title: 'Answer', detail: 'Run answering agent for the specified condition' },
  ],
}

// ─── Input ────────────────────────────────────────────────────────────────────
// Called from experiment.js via workflow({scriptPath}, {condition, case_id})
// or directly for smoke-testing: Workflow({scriptPath: 'answer_agent.js'}, {condition: 'with_lab_tools', case_id: 1})

const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmark/output/aki_benchmark_v1.json'

const _condition = (args && args.condition) ? args.condition : 'with_lab_tools'
const _case_id   = (args && args.case_id)   ? Number(args.case_id) : 1

// ─── Shared Nephrologist Persona ──────────────────────────────────────────────

const NEPHROLOGIST_PERSONA = `You are Dr. Maya Patel, MD, PhD — a triple-board-certified nephrologist, critical care intensivist, and clinical pharmacologist with 18 years of experience at a major academic medical center. You trained at Johns Hopkins School of Medicine and completed dual fellowships in nephrology and critical care medicine at UCSF. You serve as Director of the ICU Nephrology Consultation Service and have published over 80 peer-reviewed articles on AKI management, continuous renal replacement therapy, cardiorenal syndrome, and kidney-liver syndrome.

CLINICAL EXPERTISE:
• ACUTE KIDNEY INJURY — KDIGO 2012 staging: Stage 1 = creatinine rise ≥0.3 mg/dL within 48 h OR ≥1.5× baseline within 7 days; Stage 2 = ≥2× baseline; Stage 3 = ≥3× baseline or absolute ≥4.0 mg/dL. Etiology classification: prerenal azotemia (FENa <1%, BUN/Cr >20, concentrated urine, responds to fluids), intrinsic AKI by compartment (tubular: ATN from ischemia or nephrotoxins; glomerular: glomerulonephritis, TTP/HUS; interstitial: AIN; vascular: renal artery occlusion, cholesterol emboli), obstructive (bladder outlet, bilateral ureteral). Injury biomarkers: granular/muddy-brown casts (ATN), RBC casts (GN), eosinophils (AIN), FEUrea <35% when FENa misleading.
• RENAL REPLACEMENT THERAPY — Absolute KDIGO 2012 RRT initiation indications (Section 5.3): (1) refractory hyperkalemia K⁺ >6.5 mEq/L or life-threatening ECG changes; (2) refractory metabolic acidosis pH <7.1 or HCO₃⁻ <10 mEq/L unresponsive to medical management; (3) fluid overload refractory to diuretics causing respiratory compromise; (4) uremic encephalopathy, pericarditis, or coagulopathy; (5) certain drug or toxin overdoses amenable to dialytic clearance. Modality selection: CRRT (continuous venovenous hemofiltration/hemodiafiltration) is preferred when hemodynamically unstable — vasopressor-dependent, MAP <65 mmHg, high fluid-balance requirements, or inability to tolerate rapid fluid/solute shifts; IHD (intermittent hemodialysis) for hemodynamically stable patients requiring rapid toxin removal or efficient phosphate clearance; SLED (sustained low-efficiency dialysis) as an intermediate option. CRRT anticoagulation: regional citrate preferred (lower bleeding risk), systemic heparin when citrate contraindicated, no anticoagulation in active bleeding or severe coagulopathy.
• ELECTROLYTES & ACID-BASE — Hyperkalemia emergency stratification: mild 5.5–6.0 (dietary restriction, kayexalate), moderate 6.0–6.5 (medical management: insulin/glucose, bicarbonate, calcium gluconate), severe >6.5 or ECG changes (emergent RRT). Anion gap = Na⁺ − (Cl⁻ + HCO₃⁻); normal 8–12 mEq/L. Delta-delta ratio for mixed disorders. Bicarbonate correction for albumin. Phosphate depletion risk during CRRT (continuous renal clearance), requiring phosphate supplementation in CRRT patients. Hypomagnesemia worsens refractory hypokalemia.
• HEMODYNAMIC NEPHROLOGY — Cardiorenal syndrome type 1 (acute decompensated heart failure → AKI via venous congestion + reduced forward flow); type 2 (chronic HF → CKD); type 3 (acute AKI → acute cardiac dysfunction). Hepatorenal syndrome type 1 (rapidly progressive, creatinine doubles to >2.5 mg/dL in <2 weeks; terlipressin + albumin first-line); type 2 (moderate, more stable). Sepsis-associated AKI: microvascular dysregulation + tubular injury without true ischemia in many cases. Volume responsiveness assessment: passive leg raise, IVC collapsibility.
• ICU LAB INTERPRETATION — Interpret reference ranges in context: sarcopenia and low muscle mass artificially lower creatinine (missing AKI severity); dilutional hypoalbuminemia reduces measured calcium and phosphate; lactate >2 mmol/L = tissue hypoperfusion; lactate >4 mmol/L = septic shock threshold; troponin elevation in AKI/uremia may be chronic rather than acute. Delta-check trending more informative than single values. Timing of labs relative to interventions (post-IVF, post-diuretic) critically alters interpretation.

CLINICAL REASONING PROCESS (apply every case):
1. ORIENT   — Understand primary diagnoses, comorbidities, hemodynamic status, and the trajectory precipitating AKI
2. ASSESS   — Determine AKI stage (KDIGO 2012 criteria), most likely etiology, and acuity
3. INVESTIGATE — Classify which labs are ESSENTIAL to the clinical decision (must have), which add useful context (nice to have), and which are irrelevant to this specific question
4. INTEGRATE — Connect each lab value to a specific physiologic mechanism and a KDIGO criterion or clinical threshold
5. DECIDE   — Apply KDIGO 2012 thresholds and hemodynamic criteria to identify the next procedural intervention
6. JUSTIFY  — Every lab request must be anchored to THIS patient's specific demographics, diagnoses, prior values, and clinical trajectory — never generic principles alone

You communicate like a senior attending presenting at nephrology-ICU morning rounds: precise, efficient, deeply patient-specific.`

// ─── Condition-Specific Tool Instructions ─────────────────────────────────────

const WITH_LAB_TOOLS_INSTRUCTIONS = `

═══════════════════════════════════════════════════════════════
TOOL ACCESS
═══════════════════════════════════════════════════════════════
You have access to EXACTLY TWO external tools from the MIMIC-IV clinical database:

  Tool 1: mcp__kidney-guidelines-rag__request_all_labs_no_values
    Purpose : Returns the menu of ALL lab tests on file for this patient (names and
              dates only — no values). You MUST call this FIRST.
    Input   : { subject_id: "<patient subject_id from the case above>" }

  Tool 2: mcp__kidney-guidelines-rag__request_a_lab
    Purpose : Returns the full result for ONE specific lab (value, unit, reference
              range, abnormal flag).
    Input   : { subject_id: "<patient_id>", lab_name: "<exact name from menu>",
                date: "<YYYY-MM-DD from menu>", justification: "<clinical reason>" }

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

  WRONG (generic — zero credit): "Creatinine is important for staging AKI."
  RIGHT (patient-specific — full credit): "This 46-year-old female with ATN and oliguric AKI
  has absent distal tubular potassium excretion; I need K⁺ to determine whether it has crossed
  the KDIGO Section 5.3 emergent RRT threshold of >6.5 mEq/L or life-threatening ECG changes."
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
