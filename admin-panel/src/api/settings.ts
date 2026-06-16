import client from './client'

export interface AISettings {
  ar_system_prompt: string
  en_system_prompt: string
  ar_dont_know: string
  en_dont_know: string
  ar_low_conf: string
  en_low_conf: string
  lang_not_supported: string
  ar_out_of_scope: string
  en_out_of_scope: string
}

export async function getSettings(): Promise<AISettings> {
  const res = await client.get('/api/admin/settings')
  return res.data
}

export async function updateSettings(settings: Partial<AISettings>): Promise<void> {
  await client.put('/api/admin/settings', settings)
}

export async function restoreDefaults(): Promise<void> {
  await client.post('/api/admin/settings/restore')
}
