#!/usr/bin/env node
/**
 * Ollama-based experiment runner for cardiac-dirchange-v3.
 * Runs ALL 20 cases under BOTH conditions using the same Ollama model:
 *   control     — Full EHR + PubMed MCP Server access
 *   independent — Full EHR only (no PubMed)
 *
 * Both conditions get the SAME 20 cases for direct within-case comparison.
 *
 * Usage:
 *   node experiment_ollama.js                          (runs both, uses qwen3.6:latest)
 *   OLLAMA_MODEL=llama3.3:70b node experiment_ollama.js  (custom model)
 */

import { execSync } from 'child_process'
import { readFileSync, writeFileSync } from 'fs'
import path from 'path'

const AGENT_SCRIPT = path.join(process.cwd(), 'answer_agent_ollama.js')
const BENCHMARK_PATH = '/Users/krishna_arun/Documents/Summer_Work/SIMR/SIMR-Research/benchmarks/cardiac-dirchange-v3/output/cardiac_dirchange_v3_benchmark_v1.json'
const FINAL_OUTPUT   = path.join(process.cwd(), 'output/v3_ollama_results.json')

const MODEL = process.env.OLLAMA_MODEL || 'qwen3.6:latest'
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'

// ─── Run both conditions sequentially with Ollama ──────────────────────────────

console.log(`\n═══════════════════════════════════════════════════════════`)
console.log(`  cardiac-dirchange-v3: Ollama experiment`)
console.log(`  Model: ${MODEL}`)
console.log(`  Base URL: ${OLLAMA_BASE_URL}`)
console.log(`═══════════════════════════════════════════════════════════\n`)

const conditions = ['control', 'independent']
const results = {}

for (const condition of conditions) {
  console.log(`\n>>> RUNNING: ${condition.toUpperCase()} (${10} cases)\n`)

  const childCmd = `node "${AGENT_SCRIPT}" --condition ${condition}`

  try {
    execSync(childCmd, {
      cwd: process.cwd(),
      env: { ...process.env, OLLAMA_MODEL: MODEL, OLLAMA_BASE_URL: OLLAMA_BASE_URL, BENCHMARK_PATH },
      stdio: 'inherit'
    })

    // Read the saved results file
    const resultFile = path.join(process.cwd(), `output/v3_${condition}_results.json`)
    results[condition] = JSON.parse(readFileSync(resultFile, 'utf8'))
  } catch (err) {
    console.error(`\nERROR running ${condition}:`, err.message)
    process.exit(1)
  }
}

// ─── Compare results ────────────────────────────────────────────────────────────

const ctrl = results.control
const indep = results.independent

console.log('\n\n═══════════════════════════════════════════════════════════')
console.log('  COMPARISON RESULTS')
console.log('═══════════════════════════════════════════════════════════\n')

// Per-metric comparison table
const metrics = [
  { key: 'mean_score',      label: 'Mean score (max 1.0)' },
  { key: 'direction_accuracy', label: 'Direction accuracy' },
  { key: 'within_50pct_rate', label: 'Within 50%' },
  { key: 'within_20pct_rate', label: 'Within 20%' },
]

console.log('┌─────────────────────┬──────────────────┬──────────────────┬───────────┐')
console.log('│ Metric              │ Control (+PubMed)│ Independent      │ Delta     │')
console.log('├─────────────────────┼──────────────────┼──────────────────┼───────────┤')

for (const m of metrics) {
  const ctrlVal = (ctrl.summary[m.key] * 100).toFixed(1) + '%'
  const indepVal = (indep.summary[m.key] * 100).toFixed(1) + '%'
  const delta = ((ctrl.summary[m.key] - indep.summary[m.key]) * 100).toFixed(1) + '%'
  const deltaSign = delta.startsWith('-') ? '' : '+'

  console.log(`│ ${m.label.padEnd(20)} │ ${(ctrlVal + '%').padEnd(18)} │ ${(indepVal + '%').padEnd(18)} │ ${deltaSign}${delta} │`)
}

console.log('└─────────────────────┴──────────────────┴──────────────────┴───────────┘')

// Per-case comparison table
const ctrlCases = Object.fromEntries(ctrl.per_case.map(c => [c.case_id, c]))
const indepCases = Object.fromEntries(indep.per_case.map(c => [c.case_id, c]))

console.log('\n\nPer-case results:')
console.log('┌──────┬──────────┬─────────────────────────────┬─────────────────────────────┬──────────┐')
console.log('│ Case │ Reversal │ Control                     │ Independent                 │ Winner │')
console.log('├──────┼──────────┼─────────────────────────────┼─────────────────────────────┼──────────┤')

let ctrlWins = 0, indepWins = 0, tieCases = 0

const reversalMap = { 1: 'rising→falling', 2: 'rising→falling', 3: 'stable→falling',
                      4: 'falling→rising', 5: 'falling→rising', 6: 'rising→falling',
                      7: 'falling→rising', 8: 'stable→rising', 9: 'falling→rising',
                      10: 'stable→rising', 12: 'falling→rising', 13: 'rising→falling',
                      15: 'stable→rising', 18: 'stable→falling', 19: 'stable→rising',
                      21: 'falling→rising', 24: 'stable→falling', 28: 'falling→rising',
                      29: 'stable→falling', 37: 'stable→falling' }

for (const cid of Object.keys(ctrlCases).sort((a,b) => a-b)) {
  const c = ctrlCases[cid]
  const i = indepCases[cid]
  if (!i) continue

  const rev = reversalMap[cid] || '?'
  const revStr = rev.length > 12 ? rev.substring(0, 12) : rev.padEnd(12)

  const cDir = `${c.predicted_dir}(${c.score})`
  const iDir = `${i.predicted_dir}(${i.score})`

  let winner
  if (c.score > i.score) { winner = 'Control+'; ctrlWins++ }
  else if (i.score > c.score) { winner = 'Independent+'; indepWins++ }
  else { winner = 'Tie'; tieCases++ }

  console.log(`│ ${String(cid).padEnd(4)} │ ${revStr} │ ${cDir.padEnd(23)} │ ${iDir.padEnd(23)} │ ${winner.padEnd(8)} │`)
}

console.log('└──────┴──────────┴─────────────────────────────┴─────────────────────────────┴──────────┘')

// Summary stats
console.log(`\nWinner summary: Control = ${ctrlWins}, Independent = ${indepWins}, Ties = ${tieCases}`)

const ctrlDelta = (ctrl.summary.mean_score - indep.summary.mean_score) * 100
if (Math.abs(ctrlDelta) < 0.5) {
  console.log(`Conclusion: No meaningful difference between conditions (delta=${ctrlDelta.toFixed(1)} points).`)
} else if (ctrlDelta > 0) {
  console.log(`Conclusion: PubMed access HELPED by ${ctrlDelta.toFixed(1)} points on average.`)
} else {
  console.log(`Conclusion: PubMed access HURT by ${Math.abs(ctrlDelta).toFixed(1)} points on average.`)
}

// ─── Save final results ─────────────────────────────────────────────────────────

const finalResults = {
  benchmark: 'cardiac-dirchange-v3',
  model: MODEL,
  base_url: OLLAMA_BASE_URL,
  n_cases: ctrl.summary.n_cases,
  condition_definitions: {
    control:     'Full EHR + PubMed MCP Server access',
    independent: 'Full EHR only (no PubMed MCP Server)',
  },
  summary: {
    control:      ctrl.summary,
    independent:  indep.summary,
  },
  comparison_table: `
Control mean_score: ${ctrl.summary.mean_score} | direction_accuracy: ${(ctrl.summary.direction_accuracy*100).toFixed(1)}% | within_50pct: ${(ctrl.summary.within_50pct_rate*100).toFixed(1)}% | within_20pct: ${(ctrl.summary.within_20pct_rate*100).toFixed(1)}%
Independent mean_score: ${indep.summary.mean_score} | direction_accuracy: ${(indep.summary.direction_accuracy*100).toFixed(1)}% | within_50pct: ${(indep.summary.within_50pct_rate*100).toFixed(1)}% | within_20pct: ${(indep.summary.within_20pct_rate*100).toFixed(1)}%
Delta (control - independent): mean_score=${ctrlDelta.toFixed(3)}
  `.trim(),
  per_case_comparison: ctrl.per_case.map(c => ({
    case_id: c.case_id,
    reversal_type: reversalMap[c.case_id],
    control: { direction: c.predicted_dir, score: c.score },
    independent: indepCases[c.case_id] ? {
      direction: indepCases[c.case_id].predicted_dir,
      score: indepCases[c.case_id].score
    } : null,
    winner: c.score > (indepCases[c.case_id]?.score || 0) ? 'control' :
            c.score < (indepCases[c.case_id]?.score || 0) ? 'independent' : 'tie',
  })),
  winner_summary: { control: ctrlWins, independent: indepWins, tie: tieCases },
}

writeFileSync(FINAL_OUTPUT, JSON.stringify(finalResults, null, 2))
console.log(`\nFinal results saved to ${FINAL_OUTPUT}`)
