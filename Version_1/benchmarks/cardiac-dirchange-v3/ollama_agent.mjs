/**
 * Ollama agent module — accepts custom baseURL per call.
 */
import { OpenAI } from 'openai'

const DEFAULT_MODEL = process.env.OLLAMA_MODEL || 'qwen3.6:latest'

/**
 * Call the Ollama model with structured output.
 * @param {string} systemPrompt - System message (defaults to '')
 * @param {string} userPrompt   - User task prompt
 * @param {object|null} schema  - JSON Schema for structured output
 * @param {string} model         - Model name
 * @param {string} baseURL       - Ollama /v1 endpoint
 */
export async function callAgentStructured(systemPrompt, userPrompt, schema, model = DEFAULT_MODEL, baseURL = 'http://localhost:11434/v1') {
  const client = new OpenAI({ baseURL, apiKey: 'ollama' })

  try {
    const resp = await client.chat.completions.create({
      model,
      messages: [
        { role: 'system', content: systemPrompt || '' },
        { role: 'user',   content: userPrompt },
      ],
      response_format: {
        type: 'json_schema',
        json_schema: { name: 'prediction', schema, strict: false },
      },
      temperature: 0,
      max_tokens: 4096,
    })

    const raw = resp.choices?.[0]?.message?.content || ''
    return parseJSON(raw)
  } catch (err) {
    // Fallback: text response + JSON parsing
    const fallbackPrompt = userPrompt + '\n\nIMPORTANT: Your entire response must be valid JSON only — no markdown fences or explanatory text.'

    const resp = await client.chat.completions.create({
      model,
      messages: [
        { role: 'system', content: systemPrompt || '' },
        { role: 'user',   content: fallbackPrompt },
      ],
      temperature: 0,
      max_tokens: 4096,
    })

    const raw = resp.choices?.[0]?.message?.content || ''
    return parseJSON(raw)
  }
}

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
