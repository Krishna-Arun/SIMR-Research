/**
 * Ollama Qwen 3.6 agent module for causal cardiac benchmarks.
 * Adapted from cardiac-dirchange-v3/ollama_agent.mjs
 *
 * Supports:
 * - Structured JSON output via response_format
 * - Text-only output
 * - Optional PubMed MCP tool access
 * - Confidence/activation value extraction
 */

import { OpenAI } from 'openai'

const DEFAULT_MODEL = process.env.OLLAMA_MODEL || 'qwen3.6:latest'
const DEFAULT_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'

// Model name mapping for compatibility
const MODEL_ALIASES = {
  'qwen3.6': 'qwen3.6:latest',
  'qwen3.4b': 'qwen3.4b:latest',
  'qwen3.6:latest': 'qwen3.6:latest',
  'qwen3.4b:latest': 'qwen3.4b:latest',
}

/**
 * Call Qwen via Ollama with optional structured output and tool support.
 * Also extracts token logits for confidence computation.
 *
 * @param {string} systemPrompt - System message
 * @param {string} userPrompt   - User task prompt
 * @param {object|null} schema  - JSON Schema for structured output (optional)
 * @param {string} model        - Model name
 * @param {string} baseURL      - Ollama endpoint
 * @param {boolean} withPubMed  - Enable PubMed tool access (for future expansion)
 * @returns {Promise<object|string>} Parsed JSON if schema provided, else raw text; includes confidence from logits
 */
export async function callAgentStructured(systemPrompt, userPrompt, schema = null, model = DEFAULT_MODEL, baseURL = DEFAULT_BASE_URL, withPubMed = false) {
  const client = new OpenAI({ baseURL, apiKey: 'ollama' })

  const messages = [
    { role: 'system', content: systemPrompt || '' },
    { role: 'user', content: userPrompt },
  ]

  try {
    const createOpts = {
      model,
      messages,
      temperature: 0,
      max_tokens: 4096,
      logprobs: true,  // Request token log probabilities
      top_logprobs: 3, // Get top 3 alternatives for each token
    }

    // Add structured output if schema provided
    if (schema) {
      createOpts.response_format = {
        type: 'json_schema',
        json_schema: { name: 'prediction', schema, strict: false },
      }
    }

    const resp = await client.chat.completions.create(createOpts)

    const raw = resp.choices?.[0]?.message?.content || ''
    const result = schema ? parseJSON(raw) : raw

    // Extract confidence from logprobs
    const confidence = extractConfidenceFromLogprobs(resp.choices?.[0]?.logprobs)

    // Extract confidence metadata if available
    const metadata = {
      model,
      finish_reason: resp.choices?.[0]?.finish_reason,
      usage: resp.usage ? {
        prompt_tokens: resp.usage.prompt_tokens,
        completion_tokens: resp.usage.completion_tokens,
      } : null,
      confidence_from_logits: confidence,
    }

    return schema
      ? { ...result, _metadata: metadata, _confidence: confidence }
      : { text: result, _metadata: metadata, _confidence: confidence }
  } catch (err) {
    console.error(`Ollama API error (${model}):`, err.message)

    // Fallback: request raw JSON in prompt (no logprobs available in fallback)
    const fallbackPrompt = userPrompt + '\n\nIMPORTANT: Your entire response must be valid JSON only — no markdown fences or explanatory text.'

    const resp = await client.chat.completions.create({
      model,
      messages: [
        { role: 'system', content: systemPrompt || '' },
        { role: 'user', content: fallbackPrompt },
      ],
      temperature: 0,
      max_tokens: 4096,
    })

    const raw = resp.choices?.[0]?.message?.content || ''
    const result = schema ? parseJSON(raw) : raw

    const metadata = {
      model,
      fallback: true,
      finish_reason: resp.choices?.[0]?.finish_reason,
      usage: resp.usage ? {
        prompt_tokens: resp.usage.prompt_tokens,
        completion_tokens: resp.usage.completion_tokens,
      } : null,
      confidence_from_logits: null, // not available in fallback
    }

    return schema ? { ...result, _metadata: metadata } : { text: result, _metadata: metadata }
  }
}

/**
 * Extract confidence from token logits.
 * Analyzes log probabilities of key tokens to quantify model certainty.
 *
 * Metrics computed:
 * - average_logprob: mean log probability across all tokens
 * - min_logprob: lowest probability token (bottleneck)
 * - entropy: Shannon entropy of token distributions
 * - confidence_score: normalized [0, 1] confidence
 *
 * @param {object|null} logprobs - logprobs structure from OpenAI response
 * @returns {object|null} Confidence metrics
 */
function extractConfidenceFromLogprobs(logprobs) {
  if (!logprobs || !logprobs.content) {
    return null
  }

  const tokens = logprobs.content || []
  if (tokens.length === 0) {
    return null
  }

  // Collect log probabilities and probabilities
  const logProbs = []
  const probs = []
  let totalEntropy = 0

  for (const token of tokens) {
    const logp = token.logprob || 0
    logProbs.push(logp)
    probs.push(Math.exp(logp))

    // Compute entropy from top_logprobs if available
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

  // Metrics
  const avgLogprob = logProbs.reduce((a, b) => a + b, 0) / logProbs.length
  const minLogprob = Math.min(...logProbs)
  const avgProb = probs.reduce((a, b) => a + b, 0) / probs.length
  const avgEntropy = totalEntropy / tokens.length

  // Normalize logprob to [0, 1] confidence score
  // Logprobs range typically -30 to 0 for language models
  // We'll use: confidence = (logprob - min_bound) / (0 - min_bound)
  const logprobMinBound = -15.0 // empirical lower bound for reasonable responses
  const normalizedAvgLogprob = Math.max(0, Math.min(1, (avgLogprob - logprobMinBound) / (0 - logprobMinBound)))

  // Normalize entropy to [0, 1] confidence (lower entropy = higher confidence)
  // Max entropy for binary is 1.0, cap at 5.0 for safety
  const maxEntropy = 5.0
  const normalizedEntropy = Math.max(0, Math.min(1, 1 - (avgEntropy / maxEntropy)))

  // Combined confidence: weighted average
  const confidenceScore = (normalizedAvgLogprob * 0.6 + normalizedEntropy * 0.4)

  return {
    average_logprob: Math.round(avgLogprob * 1000) / 1000,
    min_logprob: Math.round(minLogprob * 1000) / 1000,
    average_probability: Math.round(avgProb * 1000) / 1000,
    average_entropy: Math.round(avgEntropy * 1000) / 1000,
    confidence_score: Math.round(confidenceScore * 1000) / 1000, // [0, 1]
    confidence_level: classifyConfidence(confidenceScore), // 'high' | 'medium' | 'low'
    n_tokens: tokens.length,
  }
}

/**
 * Classify confidence score into categorical levels.
 */
function classifyConfidence(score) {
  if (score >= 0.7) return 'high'
  if (score >= 0.4) return 'medium'
  return 'low'
}

/**
 * Parse JSON from raw text response, handling markdown code fences.
 */
function parseJSON(text) {
  const cleaned = text
    .replace(/^```[a-zA-Z]*\n?/i, '')
    .replace(/\n?```$/g, '')
    .trim()

  try { return JSON.parse(cleaned) }
  catch {
    const match = cleaned.match(/\{[\s\S]*\}/)
    if (match) return JSON.parse(match[0])
    throw new Error(`Failed to parse response as JSON:\n${text.slice(0, 500)}`)
  }
}

/**
 * Convenience: text-only response.
 */
export async function callAgentText(systemPrompt, userPrompt, model = DEFAULT_MODEL, baseURL = DEFAULT_BASE_URL) {
  return callAgentStructured(systemPrompt, userPrompt, null, model, baseURL)
}

export { DEFAULT_MODEL, DEFAULT_BASE_URL }
