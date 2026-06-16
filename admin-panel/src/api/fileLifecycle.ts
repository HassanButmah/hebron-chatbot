import client from './client'

export interface StaleFile {
  id: number
  filename: string
  original_filename: string
  status: string
  valid_until: string | null
  next_review_at: string | null
  upload_date: string | null
  reasons: string[]
}

export interface DocumentVersion {
  id: number
  version_number: number
  filename: string
  original_filename: string | null
  chunk_count: number
  content_hash: string | null
  action: string
  note: string | null
  created_at: string | null
}

export interface FreshnessPayload {
  source_url?: string
  owner?: string
  category?: string
  valid_from?: string
  valid_until?: string
  next_review_at?: string
  status?: string
}

export async function getStaleFiles(): Promise<StaleFile[]> {
  const res = await client.get('/api/admin/files/stale')
  return res.data
}

export async function getFileVersions(recordId: number): Promise<DocumentVersion[]> {
  const res = await client.get(`/api/admin/files/${recordId}/versions`)
  return res.data
}

export async function updateFileFreshness(
  recordId: number,
  payload: FreshnessPayload
): Promise<void> {
  await client.put(`/api/admin/files/${recordId}/freshness`, payload)
}

export async function markFileReviewed(recordId: number, note?: string): Promise<void> {
  await client.put(`/api/admin/files/${recordId}/review`, { note })
}

export async function replaceFile(
  recordId: number,
  file: File,
  note?: string
): Promise<{ ok: boolean; filename: string; original_filename: string; chunks: number }> {
  const form = new FormData()
  form.append('file', file)
  if (note) form.append('note', note)
  const res = await client.put(`/api/admin/files/${recordId}/replace`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 1800000,
  })
  return res.data
}

export async function retireFile(recordId: number): Promise<void> {
  await client.post(`/api/admin/files/${recordId}/retire`, {})
}

export async function restoreFile(
  recordId: number
): Promise<{ ok: boolean; filename: string; chunk_count: number; valid_until: string }> {
  const res = await client.post(`/api/admin/files/${recordId}/restore`, {})
  return res.data
}

export async function reindexFile(
  recordId: number
): Promise<{ ok: boolean; filename: string; chunk_count: number }> {
  const res = await client.post(`/api/admin/files/${recordId}/reindex`, {})
  return res.data
}
