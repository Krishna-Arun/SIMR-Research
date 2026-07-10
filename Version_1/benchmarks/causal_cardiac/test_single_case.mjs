#!/usr/bin/env node
import { callAgentStructured } from './ollama_qwen_agent.mjs'
import { readFileSync } from 'fs'

const testCase = JSON.parse(readFileSync('questions/a_001.json', 'utf8'))

const systemPrompt = `You are an expert cardiologist with deep knowledge of cardiac physiology and intervention outcomes.

Your task: Given a patient's pre-intervention clinical state and a specific procedure, predict what physiological changes (lab value direction/magnitude) you would expect in the post-intervention period.

Provide structured output with predicted changes for Troponin T, CK, CK-MB, Creatinine, BUN, Potassium.`

const schema = {
  type: 'object',
  required: ['troponin_direction', 'troponin_magnitude_pct', 'causal_justification'],
  properties: {
    troponin_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
    troponin_magnitude_pct: { type: 'number' },
    ck_direction: { type: 'string', enum: ['rising', 'falling', 'stable'] },
    causal_justification: { type: 'string' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  },
}

console.log('[TEST] Starting single case test')
console.log('[TEST] Case:', testCase.case_id)
console.log('[TEST] Calling Qwen...')

try {
  const result = await callAgentStructured(
    systemPrompt,
    testCase.question.stem,
    schema,
    'qwen3.6:latest',
    'http://localhost:11434/v1',
    false
  )

  console.log('[TEST] Success!')
  console.log('[TEST] Prediction:', JSON.stringify(result, null, 2))
  
  if (result._confidence) {
    console.log('[TEST] Confidence:', JSON.stringify(result._confidence, null, 2))
  }
} catch (err) {
  console.error('[TEST] Error:', err.message)
  process.exit(1)
}
