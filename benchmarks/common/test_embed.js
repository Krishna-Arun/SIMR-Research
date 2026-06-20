export const meta = {
  name: 'test-patient-embed',
  description: 'Minimal test: verify embedded PATIENT constant is accessible and MCP tools are callable',
  phases: [{ title: 'Test', detail: 'Single agent call to confirm data access' }],
}

// ─── patient data embedded directly as a constant ────────────────────────────
const PATIENT = {
  patient_id: "10039708",
  age: 46,
  gender: "Female",
  ground_truth: "Performance of Urinary Filtration, Multiple (Continuous Renal Replacement Therapy)",
  diagnoses: [
    "Acute kidney failure with tubular necrosis",
    "Respiratory failure, unspecified with hypoxia",
    "Non-ST elevation (NSTEMI) myocardial infarction",
    "Acute systolic (congestive) heart failure",
    "Ventilator associated pneumonia",
  ],
  lab_data: [
    { label: "Creatinine",    value: "2.2",  flag: "abnormal" },
    { label: "BUN",           value: "45",   flag: "abnormal" },
    { label: "Potassium",     value: "___",  flag: "abnormal" },
    { label: "Bicarbonate",   value: "___",  flag: "abnormal" },
    { label: "Lactate",       value: "3.4",  flag: "abnormal" },
    { label: "Troponin T",    value: "___",  flag: "abnormal" },
    { label: "NTproBNP",      value: "___",  flag: "abnormal" },
    { label: "Phosphate",     value: "1.8",  flag: "abnormal" },
    { label: "Calcium, Total",value: "6.4",  flag: "abnormal" },
    { label: "WBC",           value: "13.7", flag: "abnormal" },
    { label: "Hemoglobin",    value: "9.8",  flag: "abnormal" },
    { label: "Platelet Count",value: "121",  flag: "abnormal" },
    { label: "INR",           value: "1.3",  flag: "abnormal" },
    { label: "ALT",           value: "70",   flag: "abnormal" },
    { label: "AST",           value: "139",  flag: "abnormal" },
    { label: "Anion Gap",     value: "14",   flag: null        },
    { label: "Uric Acid",     value: "12",   flag: null        },
  ],
}

// ─── test: single agent that confirms it can see the data and call MCP tools ─
phase('Test')
log(`Patient: ${PATIENT.age}F  |  Ground truth: ${PATIENT.ground_truth}`)
log(`Lab count: ${PATIENT.lab_data.length}`)

const TEST_SCHEMA = {
  type: 'object',
  required: ['patient_age_seen', 'patient_gender_seen', 'guideline_tool_called', 'guideline_snippet'],
  properties: {
    patient_age_seen:    { type: 'number',  description: 'Echo back the patient age you were given.' },
    patient_gender_seen: { type: 'string',  description: 'Echo back the patient gender you were given.' },
    guideline_tool_called: { type: 'boolean', description: 'Did you successfully call mcp__kidney-guidelines-rag__search_kidney_guidelines?' },
    guideline_snippet:   { type: 'string',  description: 'First 200 chars of what the guideline tool returned, or "tool unavailable" if it failed.' },
  },
}

const result = await agent(
  `You are a data-access test agent. Your only job is to confirm you can read patient data and call an MCP tool.

PATIENT DATA:
  Age:    ${PATIENT.age}
  Gender: ${PATIENT.gender}
  Ground truth procedure: ${PATIENT.ground_truth}
  Diagnoses: ${PATIENT.diagnoses.join('; ')}

STEP 1: Call mcp__kidney-guidelines-rag__search_kidney_guidelines NOW with query "AKI renal replacement therapy".
  If the tool works, set guideline_tool_called = true and paste the first 200 chars of the result in guideline_snippet.
  If the tool fails or is unavailable, set guideline_tool_called = false and set guideline_snippet = "tool unavailable".

STEP 2: Return the structured output with:
  patient_age_seen = the age number you were given above
  patient_gender_seen = the gender string you were given above
  guideline_tool_called = true/false
  guideline_snippet = first 200 chars of guideline result or "tool unavailable"`,
  {
    label: 'data-access-test',
    phase: 'Test',
    schema: TEST_SCHEMA,
  }
)

log(`Result: age=${result.patient_age_seen}, gender=${result.patient_gender_seen}, guideline_called=${result.guideline_tool_called}`)
log(`Snippet: ${result.guideline_snippet}`)

return {
  patient_age_seen:      result.patient_age_seen,
  patient_gender_seen:   result.patient_gender_seen,
  guideline_tool_called: result.guideline_tool_called,
  guideline_snippet:     result.guideline_snippet,
  embedded_age_matches:  result.patient_age_seen === PATIENT.age,
  embedded_gender_matches: result.patient_gender_seen === PATIENT.gender,
}
