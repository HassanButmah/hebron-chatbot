import client from './client'

export interface LLMConfig {
  provider: 'ollama' | 'openai_compatible'
  api_base_url: string
  model_name: string
  api_key_set: boolean
}

export interface LLMTestResult {
  ok: boolean
  response_preview?: string
  error?: string
  latency_ms: number
  provider: string
  model: string
}

export async function getLLMConfig(): Promise<LLMConfig> {
  const res = await client.get('/api/admin/llm-config')
  return res.data
}

export async function saveLLMConfig(payload: {
  provider: string
  api_base_url: string
  api_key: string
  model_name: string
}): Promise<LLMConfig & { ok: boolean }> {
  const res = await client.put('/api/admin/llm-config', payload)
  return res.data
}

export async function testLLMConfig(): Promise<LLMTestResult> {
  const res = await client.get('/api/admin/llm-config/test')
  return res.data
}
