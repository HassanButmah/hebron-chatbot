import client from './client'

export interface AdminUser {
  username: string
  role: string
}

export async function login(username: string, password: string): Promise<{ token: string; username: string; role: string }> {
  const res = await client.post('/api/admin/login', { username, password })
  return res.data
}

export async function getMe(): Promise<AdminUser> {
  const res = await client.get('/api/admin/me')
  return res.data
}
