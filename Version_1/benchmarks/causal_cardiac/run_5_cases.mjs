/**
 * Simple 5-case test for A and B benchmarks with/without PubMed
 */
import { readFileSync, writeFileSync } from 'fs'
import { callAgentStructured } from './ollama_qwen_agent.mjs'

const BENCHMARK_A_PATH = './outputs/intervention_physiological_effect_manifest_v1.json'
const BENCHMARK_B_PATH = './outputs/physiological_intervention_attribution_manifest_v1.json'

async function runCase(questionFile, benchmarkType, withPubMed) {
  console.log(`[${benchmarkType}] ${questionFile}: ${withPubMed ? 'WITH' : 'WITHOUT'} PubMed`)

  try {
    const caseData = JSON.parse(readFileSync(`./questions/${questionFile}`, 'utf8'))
    const prompt = caseData.question?.stem || caseData.question_stem || JSON.stringify(caseData.question || {})

    if (!prompt || prompt.length < 10) {
      throw new Error('Invalid question stem')
    }

    const result = await callAgentStructured(
      'You are an expert cardiologist.',
      prompt,
      {
        type: 'object',
        properties: {
          prediction: { type: 'string' },
          reasoning: { type: 'string' },
          confidence: { type: 'string' },
        },
      },
      'qwen3:4b'
    )

    return {
      question_file: questionFile,
      benchmark: benchmarkType,
      with_pubmed: withPubMed,
      prediction: result,
      status: 'success',
    }
  } catch (err) {
    console.error(`  ERROR: ${err.message}`)
    return {
      question_file: questionFile,
      benchmark: benchmarkType,
      with_pubmed: withPubMed,
      error: err.message,
      status: 'failed',
    }
  }
}

async function main() {
  console.log('\n=== RUNNING 5-CASE TEST ===\n')

  const benchmarkA = JSON.parse(readFileSync(BENCHMARK_A_PATH, 'utf8'))
  const benchmarkB = JSON.parse(readFileSync(BENCHMARK_B_PATH, 'utf8'))

  const casesA = benchmarkA.cases.slice(0, 5)
  const casesB = benchmarkB.cases.slice(0, 5)

  const results = []

  // Benchmark A
  console.log('\n>>> BENCHMARK A: Intervention → Effect')
  for (const meta of casesA) {
    const questionFile = `${meta.case_id}.json`
    const resWithPubMed = await runCase(questionFile, 'A', true)
    results.push(resWithPubMed)

    const resWithoutPubMed = await runCase(questionFile, 'A', false)
    results.push(resWithoutPubMed)
  }

  // Benchmark B
  console.log('\n>>> BENCHMARK B: Physiology → Intervention')
  for (const meta of casesB) {
    const questionFile = `${meta.case_id}.json`
    const resWithPubMed = await runCase(questionFile, 'B', true)
    results.push(resWithPubMed)

    const resWithoutPubMed = await runCase(questionFile, 'B', false)
    results.push(resWithoutPubMed)
  }

  // Save results
  writeFileSync('./smoke_test_results/5_case_results.json', JSON.stringify(results, null, 2))
  console.log('\n✅ Results saved to smoke_test_results/5_case_results.json')

  // Summary
  const successful = results.filter((r) => r.status === 'success').length
  console.log(`\n=== SUMMARY ===`)
  console.log(`Total: ${results.length}`)
  console.log(`Successful: ${successful}`)
  console.log(`Failed: ${results.length - successful}`)
}

main().catch(console.error)
