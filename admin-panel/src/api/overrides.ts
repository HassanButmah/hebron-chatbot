import client from './client'

export interface Override {
  id: number
  trigger_phrase: string
  answer: string
  created_at: string | null
}

export async function listOverrides(): Promise<Override[]> {
  const res = await client.get('/api/admin/overrides')
  return res.data
}

export async function addOverride(trigger_phrase: string, answer: string): Promise<void> {
  await client.post('/api/admin/overrides', { trigger_phrase, answer })
}

export async function updateOverride(id: number, trigger_phrase: string, answer: string): Promise<void> {
  await client.put(`/api/admin/overrides/${id}`, { trigger_phrase, answer })
}

export async function deleteOverride(id: number): Promise<void> {
  await client.delete(`/api/admin/overrides/${id}`)
}
