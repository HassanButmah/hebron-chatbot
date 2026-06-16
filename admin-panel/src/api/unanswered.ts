import client from './client'

export interface UnansweredQuery {
  id: number
  question: string
  reason: string
  timestamp: string
  status: string
}

export async function listUnanswered(): Promise<UnansweredQuery[]> {
  const res = await client.get('/api/admin/unanswered')
  return res.data
}

export async function resolveQuery(id: number): Promise<void> {
  await client.put(`/api/admin/unanswered/${id}/resolve`)
}

export async function resolveAllQueries(reason?: string | null): Promise<{ resolved: number }> {
  const res = await client.post('/api/admin/unanswered/resolve-all', reason ? { reason } : {})
  return res.data
}
