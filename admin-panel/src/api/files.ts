import client from './client'

export interface FileRecord {
  id: number
  filename: string
  original_filename: string
  upload_date: string | null
  chunk_count: number
  // Lifecycle / freshness fields
  status: string
  valid_until: string | null
  next_review_at: string | null
  last_reviewed_at: string | null
  owner: string | null
  category: string | null
  source_url: string | null
}

export interface Chunk {
  page_content: string
  metadata: Record<string, unknown>
}

export async function listFiles(): Promise<FileRecord[]> {
  const res = await client.get('/files')
  return res.data
}

export async function uploadFile(file: File): Promise<{ chunks: number; filename: string; original_filename: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await client.post('/load', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 1800000,
  })
  return res.data
}

export async function deleteFile(filename: string): Promise<void> {
  await client.delete(`/files/${encodeURIComponent(filename)}`)
}

export async function getFileChunks(filename: string): Promise<Chunk[]> {
  const res = await client.get(`/files/${encodeURIComponent(filename)}/chunks`)
  return res.data
}

export function downloadUrl(filename: string): string {
  return `/files/${encodeURIComponent(filename)}/download`
}
