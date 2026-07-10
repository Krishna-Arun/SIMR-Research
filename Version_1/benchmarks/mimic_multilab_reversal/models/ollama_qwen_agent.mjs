/**
 * Ollama Qwen agent for MIMIC multi-lab reversal benchmark.
 * Reuses confidence extraction from activation function (token logits).
 *
 * Exports:
 * - callQwenStructured() — structured JSON output + confidence
 * - callQwenText() — text-only output + confidence
 */

import { OpenAI } from 'openai'

const DEFAULT_MODEL = process.env.OLLAMA_MODEL || 'qwen:latest'
const DEFAULT_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'

/**
 * Call Qwen via Ollama with structured output and confidence extraction.
 *
 * @param {string} systemPrompt - System message (role/expertise)
 * @param {string} userPrompt   - Task/case to evaluate
 * @param {object} schema       - JSON Schema for response_format
 * @param {object} opts         - Optional: { model, baseURL, temperature }
 * @returns {Promise<object>}   - { prediction, _confidence, _metadata }
 */
export async function callQwenStructured(systemPrompt, userPrompt, schema, opts = {}) {
  const {
    model = DEFAULT_MODEL,
    baseURL = DEFAULT_BASE_URL,
    temperature = 0,
  } = opts

  const client = new OpenAI({ baseURL, apiKey: 'ollama' })

  const messages = [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ]

  try {
    // Primary: structured output with logprobs
    const resp = await client.chat.completions.create({
      model,
      messages,
      temperature,
      max_tokens: 4096,
      logprobs: true,
      top_logprobs: 3,
      response_format: {
        type: 'json_schema',
        json_schema: { name: 'prediction', schema, strict: false },
      },
    })

    const raw = resp.choices?.[0]?.message?.content || ''
    const prediction = parseJSON(raw)

    // Extract confidence from token logits
    const confidence = extractConfidenceFromLogprobs(resp.choices?.[0]?.logprobs)

    const metadata = {
      model,
      finish_reason: resp.choices?.[0]?.finish_reason,
      usage: resp.usage ? {
        prompt_tokens: resp.usage.prompt_tokens,
        completion_tokens: resp.usage.completion_tokens,
      } : null,
      has_logprobs: !!confidence,
    }

    return {
      prediction,
      _confidence: confidence,
      _metadata: metadata,
    }
  } catch (err) {
    console.error(`Ollama error (${model}):`, err.message)

    // Fallback: request JSON without logprobs
    const fallbackPrompt = userPrompt + '\n\nIMPORTANT: Respond with valid JSON only.'

    const resp = await client.chat.completions.create({
      model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: fallbackPrompt },
      ],
      temperature,
      max_tokens: 4096,
    })

    const raw = resp.choices?.[0]?.message?.content || ''
    const prediction = parseJSON(raw)

    const metadata = {
      model,
      fallback: true,
      finish_reason: resp.choices?.[0]?.finish_reason,
      usage: resp.usage ? {
        prompt_tokens: resp.usage.prompt_tokens,
        completion_tokens: resp.usage.completion_tokens,
      } : null,
    }

    return {
      prediction,
      _confidence: null, // logprobs not available in fallback
      _metadata: metadata,
    }
  }
}

/**
 * Call Qwen for text-only response (no structured output).
 */
export async function callQwenText(systemPrompt, userPrompt, opts = {}) {
  const {
    model = DEFAULT_MODEL,
    baseURL = DEFAULT_BASE_URL,
    temperature = 0,
  } = opts

  const client = new OpenAI({ baseURL, apiKey: 'ollama' })

  const messages = [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ]

  try {
    const resp = await client.chat.completions.create({
      model,
      messages,
      temperature,
      max_tokens: 4096,
      logprobs: true,
      top_logprobs: 3,
    })

    const text = resp.choices?.[0]?.message?.content || ''
    const confidence = extractConfidenceFromLogprobs(resp.choices?.[0]?.logprobs)

    const metadata = {
      model,
      finish_reason: resp.choices?.[0]?.finish_reason,
      usage: resp.usage ? {
        prompt_tokens: resp.usage.prompt_tokens,
        completion_tokens: resp.usage.completion_tokens,
      } : null,
      has_logprobs: !!confidence,
    }

    return {
      text,
      _confidence: confidence,
      _metadata: metadata,
    }
  } catch (err) {
    console.error(`Ollama error (${model}):`, err.message)
    throw err
  }
}

/**
 * Extract confidence metrics from token logprobs.
 *
 * Returns object with:
 * - average_logprob: mean log probability
 * - min_logprob: lowest probability token
 * - average_probability: mean exp(logprob)
 * - average_entropy: Shannon entropy of token distributions
 * - confidence_score: normalized [0,1] score (60% logprob + 40% entropy)
 * - confidence_level: categorical ('high'|'medium'|'low')
 * - n_tokens: response length
 */
function extractConfidenceFromLogprobs(logprobs) {
  if (!logprobs || !logprobs.content) {
    return null
  }

  const tokens = logprobs.content || []
  if (tokens.length === 0) {
    return null
  }

  const logProbs = []
  const probs = []
  let totalEntropy = 0

  for (const token of tokens) {
    const logp = token.logprob || 0
    logProbs.push(logp)
    probs.push(Math.exp(logp))

    // Entropy from top_logprobs distribution
    if (token.top_logprobs && token.top_logprobs.length > 0) {
      let tokenEntropy = 0
      const topProbs = token.top_logprobs.map(t => Math.exp(t.logprob))
      const sum = topProbs.reduce((a, b) => a + b, 0)

      for (const p of topProbs) {
        const normalized = p / sum
        if (normalized > 0) {
          tokenEntropy -= normalized * Math.log2(normalized)
        }
      }
      totalEntropy += tokenEntropy
    }
  }

  const avgLogprob = logProbs.reduce((a, b) => a + b, 0) / logProbs.length
  const minLogprob = Math.min(...logProbs)
  const avgProb = probs.reduce((a, b) => a + b, 0) / probs.length
  const avgEntropy = totalEntropy / tokens.length

  // Normalize: logprobs typically range -30 to 0
  const logprobMinBound = -15.0
  const normalizedAvgLogprob = Math.max(0, Math.min(1, (avgLogprob - logprobMinBound) / (0 - logprobMinBound)))

  // Entropy normalization: lower entropy = higher confidence
  const maxEntropy = 5.0
  const normalizedEntropy = Math.max(0, Math.min(1, 1 - (avgEntropy / maxEntropy)))

  // Combined: 60% logprob + 40% entropy
  const confidenceScore = normalizedAvgLogprob * 0.6 + normalizedEntropy * 0.4

  return {
    average_logprob: round3(avgLogprob),
    min_logprob: round3(minLogprob),
    average_probability: round3(avgProb),
    average_entropy: round3(avgEntropy),
    confidence_score: round3(confidenceScore), // [0, 1]
    confidence_level: classifyConfidence(confidenceScore),
    n_tokens: tokens.length,
  }
}

/**
 * Classify confidence score into categorical level.
 */
function classifyConfidence(score) {
  if (score >= 0.7) return 'high'
  if (score >= 0.4) return 'medium'
  return 'low'
}

/**
 * Parse JSON from response, handling markdown code fences.
 */
function parseJSON(text) {
  const cleaned = text
    .replace(/^```[a-zA-Z]*\n?/i, '')
    .replace(/\n?```$/g, '')
    .trim()

  try {
    return JSON.parse(cleaned)
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/)
    if (match) {
      return JSON.parse(match[0])
    }
    throw new Error(`Failed to parse JSON: ${text.slice(0, 300)}`)
  }
}

/**
 * Round to 3 decimal places.
 */
function round3(num) {
  return Math.round(num * 1000) / 1000
}

export { DEFAULT_MODEL, DEFAULT_BASE_URL }
