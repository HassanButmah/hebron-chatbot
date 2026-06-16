import client from './client'

export interface AnalyticsData {
  total_sessions: number
  total_messages: number
  /** Distinct non-empty user_id values on chat sessions (widget/browser identity). */
  unique_users: number
  likes: number
  dislikes: number
  daily_chats: Record<string, number>
  avg_response_time: number
}

export async function getAnalytics(): Promise<AnalyticsData> {
  const res = await client.get('/admin/analytics')
  return res.data
}
