import client from './client'

export interface FAQ {
  id: number
  question: string
  answer: string
  display_order: number
  question_count: number
  created_at: string | null
}

export async function listFAQs(): Promise<FAQ[]> {
  const res = await client.get('/api/admin/faqs')
  return res.data
}

export async function addFAQ(question: string, answer: string): Promise<void> {
  await client.post('/api/admin/faqs', { question, answer })
}

export async function updateFAQ(id: number, question: string, answer: string, display_order: number): Promise<void> {
  await client.put(`/api/admin/faqs/${id}`, { question, answer, display_order })
}

export async function deleteFAQ(id: number): Promise<void> {
  await client.delete(`/api/admin/faqs/${id}`)
}

export async function normalizeFAQOrder(): Promise<void> {
  await client.post('/api/admin/faqs/normalize')
}
