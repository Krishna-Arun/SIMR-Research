/**
 * Ollama-based agent module for cardiac-dirchange-v2 benchmark.
 * Uses OpenAI Node.js SDK with custom baseURL pointing at Ollama's /v1/ endpoint.
 * Replaces Claude Code's built-in `agent()` primitive.
 */

import { OpenAI } from 'openai'

const DEFAULT_MODEL = process.env.OLLAMA_MODEL || 'qwen3.6:latest'
const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1'

// ─── Client ──────────────────────────────────────────────────────────────────

const client = new OpenAI({
  baseURL: OLLAMA_BASE_URL,
  apiKey: 'ollama', // required by the SDK, ignored in practice
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Convert a JSON Schema (JS object) to an OpenAI-compatible JSON schema.
 */
function toOpenAISchema(schema) {
  return schema
}

/**
 * Parse JSON from a raw text response, trying multiple strategies.
 */
async function extractJSON(text) {
  // Strip markdown code fences if present
  const cleaned = text
    .replace(/^```[a-zA-Z]*\n?/i, '')
    .replace(/\n?```$/g, '')
    .trim()

  try {
    return JSON.parse(cleaned)
  } catch {
    // Try to find JSON object in the middle of text
    const match = cleaned.match(/\{[\s\S]*\}/)
    if (match) {
      return JSON.parse(match[0])
    }
    throw new Error(`Failed to parse response as JSON:\n${text.slice(0, 500)}`)
  }
}

// ─── Core agent call ──────────────────────────────────────────────────────────

/**
 * Call the Ollama model with optional structured output.
 *
 * @param {string} systemPrompt - System message for the agent
 * @param {string} userPrompt - User message / task prompt
 * @param {object|null} schema - JSON Schema object (optional). If provided, attempts structured output first, falls back to text+JSON parsing.
 * @param {string} model - Model name (default: from env or 'qwen3.6:latest')
 * @returns {Promise<object|string>} Parsed structured output if schema provided, else raw response string
 */
export async function callAgent(systemPrompt, userPrompt, schema = null, model = DEFAULT_MODEL) {
  const messages = [
    { role: 'system', content: systemPrompt },
    { role: 'user',   content: userPrompt },
  ]

  try {
    if (schema) {
      // Try structured output via response_format JSON schema
      const resp = await client.chat.completions.create({
        model: model,
        messages: messages,
        response_format: {
          type: 'json_schema',
          json_schema: {
            name: 'prediction',
            schema: toOpenAISchema(schema),
            strict: false,
          },
        },
        temperature: 0,
        max_tokens: 4096,
      })

      const raw = resp.choices[0]?.message?.content || ''
      return await extractJSON(raw)
    }

    // No schema — just get text
    const resp = await client.chat.completions.create({
      model: model,
      messages: messages,
      temperature: 0,
      max_tokens: 4096,
    })

    return resp.choices[0]?.message?.content || ''

  } catch (err) {
    console.error(`Ollama API error (${model}):`, err.message)

    // Fall back to text response with structured output hint in prompt
    const fallbackPrompt = userPrompt + '\n\nIMPORTANT: Your entire response must be valid JSON. Do not include any markdown code fences or explanatory text — only output the raw JSON object.'

    const resp = await client.chat.completions.create({
      model: model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user',   content: fallbackPrompt },
      ],
      temperature: 0,
      max_tokens: 4096,
    })

    const raw = resp.choices[0]?.message?.content || ''

    if (schema) {
      return await extractJSON(raw)
    }
    return raw
  }
}

/**
 * Convenience wrapper for structured output only.
 */
export async function callAgentStructured(systemPrompt, userPrompt, schema, model = DEFAULT_MODEL) {
  return callAgent(systemPrompt, userPrompt, schema, model)
}

/**
 * Convenience wrapper for text-only output.
 */
export async function callAgentText(systemPrompt, userPrompt, model = DEFAULT_MODEL) {
  return callAgent(systemPrompt, userPrompt, null, model)
}

export { client, DEFAULT_MODEL, OLLAMA_BASE_URL }
