export const meta = {
  name: 'test-generator-patient',
  description: 'Test: generator uses embedded PATIENT constant and writes correct age/gender in question stem',
  phases: [
    { title: 'Generate', detail: 'Generator writes a question stem' },
    { title: 'Verify',   detail: 'Second agent checks age and gender in the stem' },
  ],
}

// ─── embedded patient constant ────────────────────────────────────────────────
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
    { label: "Creatinine",     value: "2.2",  flag: "abnormal" },
    { label: "BUN",            value: "45",   flag: "abnormal" },
    { label: "Potassium",      value: "___",  flag: "abnormal" },
    { label: "Bicarbonate",    value: "___",  flag: "abnormal" },
    { label: "Lactate",        value: "3.4",  flag: "abnormal" },
    { label: "Troponin T",     value: "___",  flag: "abnormal" },
    { label: "NTproBNP",       value: "___",  flag: "abnormal" },
    { label: "Phosphate",      value: "1.8",  flag: "abnormal" },
    { label: "Calcium, Total", value: "6.4",  flag: "abnormal" },
    { label: "WBC",            value: "13.7", flag: "abnormal" },
    { label: "Anion Gap",      value: "14",   flag: null },
    { label: "TSH",            value: "N/A",  flag: null },
    { label: "Lipase",         value: "N/A",  flag: null },
  ],
}

const GEN_SCHEMA = {
  type: 'object',
  required: ['question_stem', 'reasoning_gap'],
  properties: {
    question_stem: { type: 'string' },
    reasoning_gap: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['age_in_stem', 'gender_in_stem', 'age_correct', 'gender_correct', 'lab_values_leaked'],
  properties: {
    age_in_stem:      { type: 'string',  description: 'Exact age phrase found in the stem, e.g. "46-year-old"' },
    gender_in_stem:   { type: 'string',  description: 'Exact gender phrase found in the stem, e.g. "female" or "male"' },
    age_correct:      { type: 'boolean', description: 'True if stem says age 46' },
    gender_correct:   { type: 'boolean', description: 'True if stem says female/woman (not male/man)' },
    lab_values_leaked:{ type: 'boolean', description: 'True if any numeric lab value appears in the stem (e.g. "creatinine 2.2")' },
  },
}

// ─── step 1: generate a question stem ────────────────────────────────────────
phase('Generate')
log(`Generating question for patient: ${PATIENT.age}-year-old ${PATIENT.gender}`)

const gen = await agent(
  `You are writing a benchmark question for a real AKI patient.

PATIENT (use these EXACT demographics — do NOT change them):
  Age:    ${PATIENT.age}
  Gender: ${PATIENT.gender}
  Diagnoses: ${PATIENT.diagnoses.join('; ')}

AVAILABLE LABS (do NOT put values in the question):
${PATIENT.lab_data.map(l => `  ${l.label}: ${l.value}`).join('\n')}

Write a question stem that:
1. Starts with "A ${PATIENT.age}-year-old ${PATIENT.gender} ..."
2. Describes the patient using their diagnoses (no lab values, no numeric results)
3. Ends with "What is the next most probable major procedural intervention for this patient?"

Also write a one-sentence reasoning_gap explaining what labs are missing.`,
  { label: 'gen-test', phase: 'Generate', schema: GEN_SCHEMA }
)

log(`Stem (first 120): ${gen.question_stem.slice(0, 120)}`)

// ─── step 2: verify the stem has correct demographics and no leaked values ────
phase('Verify')

const verify = await agent(
  `Read this question stem carefully and answer four questions about it.

QUESTION STEM:
"""
${gen.question_stem}
"""

REQUIRED: age must be 46, gender must be Female.

1. What exact age phrase appears in the stem? (e.g. "46-year-old", "70-year-old", "elderly")
2. What exact gender phrase appears? (e.g. "female", "male", "woman", "man")
3. Is the age 46? true/false
4. Is the gender female/woman (not male/man)? true/false
5. Does the stem contain any numeric lab values (e.g. "creatinine 2.2", "potassium 6.8")? true/false`,
  { label: 'verify-test', phase: 'Verify', schema: VERIFY_SCHEMA }
)

log(`Age in stem: "${verify.age_in_stem}"  correct=${verify.age_correct}`)
log(`Gender in stem: "${verify.gender_in_stem}"  correct=${verify.gender_correct}`)
log(`Lab values leaked: ${verify.lab_values_leaked}`)

return {
  age_correct:       verify.age_correct,
  gender_correct:    verify.gender_correct,
  lab_values_leaked: verify.lab_values_leaked,
  age_in_stem:       verify.age_in_stem,
  gender_in_stem:    verify.gender_in_stem,
  question_stem:     gen.question_stem,
  all_pass:          verify.age_correct && verify.gender_correct && !verify.lab_values_leaked,
}
