import client from './client'

export interface ChatMessage {
  id: number
  role: string
  content: string
  timestamp: string | null
  feedback: 'like' | 'dislike' | null
  generation_time: number | null
}

export interface ChatSession {
  session_id: string
  title: string
  start_time: string | null
  last_message_time: string | null
  user_id?: string | null
  messages: ChatMessage[]
}

export async function getChatHistory(limit = 50): Promise<ChatSession[]> {
  const res = await client.get('/admin/chat-history', { params: { limit } })
  return res.data
}

export async function deleteSession(sessionId: string): Promise<void> {
  await client.delete(`/sessions/${encodeURIComponent(sessionId)}`)
}
