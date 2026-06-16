import client from './client'

export interface DynamicSource {
  id: number
  name: string
  source_type: string
  endpoint_url: string | null
  sync_frequency: string
  // Phase-2 scheduling
  schedule_type: string       // 'manual' | 'daily' | 'weekly' | 'monthly'
  sync_times: string          // comma-separated HH:MM, e.g. "06:00,13:00"
  schedule_day: string        // weekly: comma-sep APScheduler day_of_week "0,2,4"
  schedule_month_day: string  // monthly: comma-sep day-of-month "1,15"
  is_enabled: boolean
  last_sync_at: string | null
  status: string
  error_message: string | null
  auth_token: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SyncRun {
  id: number
  source_id: number
  status: string
  started_at: string | null
  ended_at: string | null
  records_fetched: number
  records_changed: number
  chunks_updated: number
  error_message: string | null
}

export interface SchedulerJob {
  job_id: string
  source_id: number | null
  source_name: string
  next_run_time: string | null
  trigger: string
}

export interface CreateSourcePayload {
  name: string
  source_type: string
  endpoint_url?: string
  sync_frequency?: string
  is_enabled?: boolean
  auth_token?: string
  schedule_type?: string
  sync_times?: string
  schedule_day?: string
  schedule_month_day?: string
}

export async function getSchedulerJobs(): Promise<{ jobs: SchedulerJob[]; total: number }> {
  const res = await client.get('/api/admin/scheduler/jobs')
  return res.data
}

export async function listDynamicSources(): Promise<DynamicSource[]> {
  const res = await client.get('/api/admin/dynamic-sources')
  return res.data
}

export async function createDynamicSource(payload: CreateSourcePayload): Promise<DynamicSource> {
  const res = await client.post('/api/admin/dynamic-sources', payload)
  return res.data
}

export async function updateDynamicSource(
  id: number,
  payload: Partial<CreateSourcePayload>
): Promise<DynamicSource> {
  const res = await client.put(`/api/admin/dynamic-sources/${id}`, payload)
  return res.data
}

export async function deleteDynamicSource(id: number): Promise<void> {
  await client.delete(`/api/admin/dynamic-sources/${id}`)
}

export async function syncDynamicSource(id: number): Promise<Record<string, unknown>> {
  const res = await client.post(`/api/admin/dynamic-sources/${id}/sync`, {})
  return res.data
}

export async function getSyncRuns(id: number): Promise<SyncRun[]> {
  const res = await client.get(`/api/admin/dynamic-sources/${id}/runs`)
  return res.data
}

export interface DynamicChunk {
  page_content: string
  metadata: Record<string, unknown>
}

export async function getDynamicSourceChunks(
  id: number
): Promise<{ chroma_key: string; chunks: DynamicChunk[] }> {
  const res = await client.get(`/api/admin/dynamic-sources/${id}/chunks`)
  return res.data
}

export interface ToolRoutingEndpoint {
  reachable: boolean
  status_code?: number
  error?: string
}

export interface ToolRoutingStatus {
  llm_provider: string
  tools_enabled: boolean
  mock_api_base: string
  mock_api_connectivity: {
    calendar: ToolRoutingEndpoint
    announcements: ToolRoutingEndpoint
    admissions: ToolRoutingEndpoint
    fees: ToolRoutingEndpoint
    faculty: ToolRoutingEndpoint
  }
}

export async function getToolRoutingStatus(): Promise<ToolRoutingStatus> {
  const res = await client.get('/api/admin/tool-routing/status')
  return res.data
}
