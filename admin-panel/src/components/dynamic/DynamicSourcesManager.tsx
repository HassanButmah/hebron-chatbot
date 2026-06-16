import { useState, useCallback, useEffect } from 'react'
import {
  listDynamicSources,
  createDynamicSource,
  updateDynamicSource,
  deleteDynamicSource,
  syncDynamicSource,
  getSyncRuns,
  getDynamicSourceChunks,
  getSchedulerJobs,
  getToolRoutingStatus,
  DynamicSource,
  SyncRun,
  DynamicChunk,
  SchedulerJob,
  ToolRoutingStatus,
} from '../../api/dynamicSources'
import { useData } from '../../hooks/useData'

// ─── constants ──────────────────────────────────────────────────────────────

const SOURCE_TYPES = [
  { value: 'calendar',      label: 'التقويم الأكاديمي' },
  { value: 'announcements', label: 'الإعلانات والأخبار' },
  { value: 'admissions',    label: 'القبول والتسجيل' },
  { value: 'fees',          label: 'الرسوم الجامعية' },
  { value: 'faculty',       label: 'أعضاء هيئة التدريس' },
  { value: 'generic',       label: 'عام' },
]

const SCHEDULE_TYPES = [
  { value: 'manual',  label: 'يدوي فقط' },
  { value: 'daily',   label: 'يومياً' },
  { value: 'weekly',  label: 'أسبوعياً' },
  { value: 'monthly', label: 'شهرياً' },
]

// APScheduler day_of_week: 0 = Monday … 6 = Sunday
const WEEK_DAYS = [
  { value: '0', label: 'الاثنين' },
  { value: '1', label: 'الثلاثاء' },
  { value: '2', label: 'الأربعاء' },
  { value: '3', label: 'الخميس' },
  { value: '4', label: 'الجمعة' },
  { value: '5', label: 'السبت' },
  { value: '6', label: 'الأحد' },
]

const MONTH_DAYS = Array.from({ length: 31 }, (_, i) => String(i + 1))

// ─── helpers ─────────────────────────────────────────────────────────────────

function statusBadge(status: string) {
  const map: Record<string, string> = {
    ok:             'bg-green-100 text-green-800 border-green-200',
    error:          'bg-red-100 text-red-800 border-red-200',
    syncing:        'bg-blue-100 text-blue-800 border-blue-200',
    not_configured: 'bg-gray-100 text-gray-600 border-gray-200',
    skipped:        'bg-yellow-100 text-yellow-800 border-yellow-200',
    running:        'bg-blue-100 text-blue-800 border-blue-200',
    success:        'bg-green-100 text-green-800 border-green-200',
  }
  const cls = map[status] ?? 'bg-gray-100 text-gray-600 border-gray-200'
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${cls}`}>
      {status}
    </span>
  )
}

function scheduleLabel(src: DynamicSource): string {
  const t = src.schedule_type || 'manual'
  if (t === 'manual') return 'يدوي'
  const times = (src.sync_times || '').split(',').filter(Boolean)
  const timeStr = times.join(', ')
  if (t === 'daily') return `يومياً — ${timeStr || '—'}`
  if (t === 'weekly') {
    const days = (src.schedule_day || '').split(',').filter(Boolean)
    const dayLabels = days.map(d => WEEK_DAYS.find(w => w.value === d)?.label ?? d).join('، ')
    return `أسبوعياً (${dayLabels || '—'}) — ${timeStr || '—'}`
  }
  if (t === 'monthly') {
    const mdays = (src.schedule_month_day || '').split(',').filter(Boolean)
    return `شهرياً (أيام: ${mdays.join(', ') || '—'}) — ${timeStr || '—'}`
  }
  return t
}

// ─── ScheduleEditor sub-component ────────────────────────────────────────────

interface ScheduleState {
  schedule_type: string
  times: string[]          // array of "HH:MM" strings
  schedule_day: string[]   // weekly: day indices e.g. ["0","3"]
  schedule_month_day: string[] // monthly: day numbers e.g. ["1","15"]
}

function scheduleStateToPayload(s: ScheduleState) {
  return {
    schedule_type:     s.schedule_type,
    sync_times:        s.times.filter(Boolean).join(','),
    schedule_day:      s.schedule_day.join(','),
    schedule_month_day: s.schedule_month_day.join(','),
  }
}

function payloadToScheduleState(src: Partial<DynamicSource>): ScheduleState {
  return {
    schedule_type:     src.schedule_type || 'manual',
    times:             (src.sync_times || '').split(',').filter(Boolean),
    schedule_day:      (src.schedule_day || '').split(',').filter(Boolean),
    schedule_month_day:(src.schedule_month_day || '').split(',').filter(Boolean),
  }
}

interface ScheduleEditorProps {
  value: ScheduleState
  onChange: (s: ScheduleState) => void
}

function ScheduleEditor({ value, onChange }: ScheduleEditorProps) {
  const set = (patch: Partial<ScheduleState>) => onChange({ ...value, ...patch })

  const addTime = () => set({ times: [...value.times, '08:00'] })
  const removeTime = (i: number) => set({ times: value.times.filter((_, idx) => idx !== i) })
  const setTime = (i: number, v: string) => {
    const t = [...value.times]
    t[i] = v
    set({ times: t })
  }

  const toggleDay = (d: string) => {
    const next = value.schedule_day.includes(d)
      ? value.schedule_day.filter(x => x !== d)
      : [...value.schedule_day, d].sort()
    set({ schedule_day: next })
  }

  const toggleMDay = (d: string) => {
    const next = value.schedule_month_day.includes(d)
      ? value.schedule_month_day.filter(x => x !== d)
      : [...value.schedule_month_day, d].sort((a, b) => Number(a) - Number(b))
    set({ schedule_month_day: next })
  }

  const showTimes  = value.schedule_type !== 'manual'
  const showDays   = value.schedule_type === 'weekly'
  const showMDays  = value.schedule_type === 'monthly'

  return (
    <div className="space-y-4 p-4 bg-blue-50 rounded-xl border border-blue-200">
      <p className="text-xs font-semibold text-blue-800 uppercase tracking-wide">⏰ جدولة المزامنة التلقائية</p>

      {/* Schedule type */}
      <div>
        <label className="label">نوع الجدولة</label>
        <div className="flex flex-wrap gap-2 mt-1">
          {SCHEDULE_TYPES.map(st => (
            <button
              key={st.value}
              type="button"
              onClick={() => set({ schedule_type: st.value })}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                value.schedule_type === st.value
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'
              }`}
            >
              {st.label}
            </button>
          ))}
        </div>
      </div>

      {/* Day-of-week (weekly) */}
      {showDays && (
        <div>
          <label className="label">أيام الأسبوع</label>
          <div className="flex flex-wrap gap-2 mt-1">
            {WEEK_DAYS.map(wd => (
              <button
                key={wd.value}
                type="button"
                onClick={() => toggleDay(wd.value)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                  value.schedule_day.includes(wd.value)
                    ? 'bg-indigo-600 text-white border-indigo-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:border-indigo-400'
                }`}
              >
                {wd.label}
              </button>
            ))}
          </div>
          {value.schedule_day.length === 0 && (
            <p className="text-xs text-amber-600 mt-1">اختر يوماً واحداً على الأقل.</p>
          )}
        </div>
      )}

      {/* Day-of-month (monthly) */}
      {showMDays && (
        <div>
          <label className="label">أيام الشهر</label>
          <div className="flex flex-wrap gap-1.5 mt-1 max-h-28 overflow-y-auto p-1">
            {MONTH_DAYS.map(d => (
              <button
                key={d}
                type="button"
                onClick={() => toggleMDay(d)}
                className={`w-9 h-9 rounded-lg text-sm font-medium border transition-colors ${
                  value.schedule_month_day.includes(d)
                    ? 'bg-purple-600 text-white border-purple-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:border-purple-400'
                }`}
              >
                {d}
              </button>
            ))}
          </div>
          {value.schedule_month_day.length === 0 && (
            <p className="text-xs text-amber-600 mt-1">اختر يوماً واحداً على الأقل.</p>
          )}
        </div>
      )}

      {/* Time list */}
      {showTimes && (
        <div>
          <label className="label">أوقات المزامنة اليومية</label>
          <p className="text-xs text-gray-500 mb-2">يمكنك إضافة أكثر من وقت. الصيغة: HH:MM (24 ساعة)</p>
          <div className="space-y-2">
            {value.times.map((t, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="time"
                  value={t}
                  onChange={e => setTime(i, e.target.value)}
                  className="input w-36 text-center font-mono"
                />
                {value.times.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeTime(i)}
                    className="text-red-500 hover:text-red-700 text-sm"
                    title="احذف هذا الوقت"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
            {value.times.length === 0 && (
              <p className="text-xs text-amber-600">أضف وقتاً واحداً على الأقل.</p>
            )}
          </div>
          <button
            type="button"
            onClick={addTime}
            className="mt-2 text-sm text-blue-600 hover:underline flex items-center gap-1"
          >
            ＋ إضافة وقت آخر
          </button>
        </div>
      )}

      {/* Summary */}
      {value.schedule_type !== 'manual' && value.times.length > 0 && (
        <p className="text-xs text-blue-700 bg-blue-100 rounded-lg px-3 py-2">
          📅 ملخص: مزامنة{' '}
          {value.schedule_type === 'daily'   ? 'يومياً' : ''}
          {value.schedule_type === 'weekly'  ? `كل (${value.schedule_day.map(d => WEEK_DAYS.find(w => w.value === d)?.label).filter(Boolean).join('، ') || '—'})` : ''}
          {value.schedule_type === 'monthly' ? `في أيام (${value.schedule_month_day.join(', ') || '—'}) من كل شهر` : ''}
          {' '}على الساعات: {value.times.join(' ،')}
        </p>
      )}
    </div>
  )
}

// ─── Main form state ──────────────────────────────────────────────────────────

const emptyForm = {
  name: '',
  source_type: 'calendar',
  endpoint_url: '',
  is_enabled: true,
  auth_token: '',
}

const emptySchedule: ScheduleState = {
  schedule_type: 'manual',
  times: [],
  schedule_day: [],
  schedule_month_day: [],
}

// ─── ToolRoutingStatusCard sub-component ─────────────────────────────────────

function EndpointDot({ ep }: { ep: { reachable: boolean; error?: string } | undefined }) {
  if (!ep) return <span className="text-gray-400 text-xs">—</span>
  return ep.reachable
    ? <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500" title="متصل" />
    : <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-400" title={ep.error ?? 'غير متصل'} />
}

function ToolRoutingStatusCard() {
  const [status, setStatus] = useState<ToolRoutingStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(false)
    try {
      setStatus(await getToolRoutingStatus())
    } catch {
      setErr(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const providerLabel = status
    ? status.llm_provider === 'openai_compatible'
      ? 'OpenAI-compatible (DeepSeek / …)'
      : 'Ollama (محلي)'
    : '—'

  const conn = status?.mock_api_connectivity

  return (
    <div className="card border border-indigo-200 bg-indigo-50 mb-2">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-indigo-900">🔀 حالة توجيه الأدوات (Tool Routing)</h3>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-indigo-600 hover:underline disabled:opacity-50"
        >
          {loading ? 'جاري الفحص...' : '🔄 إعادة الفحص'}
        </button>
      </div>

      {err && (
        <p className="text-xs text-red-600">تعذر جلب حالة التوجيه — تأكد من تشغيل خادم API.</p>
      )}

      {!err && status && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-indigo-800">
          <div>
            <span className="font-medium">مزوّد الذكاء الاصطناعي: </span>
            <code className="bg-indigo-100 px-1 rounded">{providerLabel}</code>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-medium">الأدوات مفعّلة:</span>
            {status.tools_enabled
              ? <span className="text-green-700 font-semibold">✅ نعم</span>
              : <span className="text-amber-700">⚠️ لا — اضبط <code className="bg-indigo-100 px-1 rounded">LLM_PROVIDER=openai_compatible</code></span>
            }
          </div>
          {conn && (
            <div className="sm:col-span-2">
              <p className="font-medium mb-1">اتصال Mock API ({status.mock_api_base}):</p>
              <div className="flex flex-wrap gap-4">
                {(['calendar', 'announcements', 'admissions', 'fees', 'faculty'] as const).map(key => (
                  <div key={key} className="flex items-center gap-1.5">
                    <EndpointDot ep={conn[key]} />
                    <span>{
                      key === 'calendar'      ? 'التقويم' :
                      key === 'announcements' ? 'الإعلانات' :
                      key === 'admissions'    ? 'القبول' :
                      key === 'fees'         ? 'الرسوم' : 'هيئة التدريس'
                    }</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DynamicSourcesManager() {
  const { data: sources, loading, error, refresh } = useData(listDynamicSources)
  const [form, setForm]           = useState({ ...emptyForm })
  const [schedule, setSchedule]   = useState<ScheduleState>({ ...emptySchedule })
  const [editingId, setEditingId] = useState<number | null>(null)
  const [saving, setSaving]       = useState(false)
  const [msg, setMsg]             = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [syncing, setSyncing]         = useState<number | null>(null)
  const [syncResult, setSyncResult]   = useState<Record<number, Record<string, unknown>>>({})
  const [runsForId, setRunsForId]     = useState<number | null>(null)
  const [runs, setRuns]               = useState<SyncRun[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const [chunksForId, setChunksForId]       = useState<number | null>(null)
  const [chunks, setChunks]                 = useState<DynamicChunk[]>([])
  const [chunksKey, setChunksKey]           = useState('')
  const [chunksLoading, setChunksLoading]   = useState(false)
  const [expandedChunkIdx, setExpandedChunkIdx] = useState<number | null>(null)

  const [showJobs, setShowJobs]     = useState(false)
  const [jobs, setJobs]             = useState<SchedulerJob[]>([])
  const [jobsLoading, setJobsLoading] = useState(false)

  const formatDate = (d: string | null) => {
    if (!d) return '—'
    try { return new Date(d).toLocaleString('ar-SA', { timeZone: 'Asia/Hebron' }) }
    catch { return d }
  }

  const startEdit = (src: DynamicSource) => {
    setEditingId(src.id)
    setForm({
      name:         src.name,
      source_type:  src.source_type,
      endpoint_url: src.endpoint_url ?? '',
      is_enabled:   src.is_enabled,
      auth_token:   src.auth_token ?? '',
    })
    setSchedule(payloadToScheduleState(src))
    setMsg(null)
  }

  const cancelEdit = () => {
    setEditingId(null)
    setForm({ ...emptyForm })
    setSchedule({ ...emptySchedule })
    setMsg(null)
  }

  const handleSave = useCallback(async () => {
    setSaving(true)
    setMsg(null)
    try {
      const payload = {
        ...form,
        endpoint_url: form.endpoint_url.trim() || undefined,
        auth_token:   form.auth_token.trim() || undefined,
        ...scheduleStateToPayload(schedule),
      }
      if (editingId !== null) {
        await updateDynamicSource(editingId, payload)
        setMsg({ type: 'success', text: 'تم تحديث المصدر وجدولته بنجاح.' })
      } else {
        await createDynamicSource(payload)
        setMsg({ type: 'success', text: 'تم إنشاء المصدر وجدولته بنجاح.' })
      }
      cancelEdit()
      refresh()
    } catch (e: unknown) {
      const err = (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'فشل الحفظ'
      setMsg({ type: 'error', text: err })
    } finally {
      setSaving(false)
    }
  }, [form, schedule, editingId, refresh])

  const handleSync = useCallback(async (id: number) => {
    setSyncing(id)
    setSyncResult(prev => ({ ...prev, [id]: {} }))
    try {
      const result = await syncDynamicSource(id)
      setSyncResult(prev => ({ ...prev, [id]: result }))
      refresh()
    } catch (e: unknown) {
      const err = (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'فشل المزامنة'
      setSyncResult(prev => ({ ...prev, [id]: { error: err } }))
    } finally {
      setSyncing(null)
    }
  }, [refresh])

  const handleDelete = useCallback(async (id: number) => {
    try {
      await deleteDynamicSource(id)
      setConfirmDelete(null)
      refresh()
    } catch {
      setMsg({ type: 'error', text: 'تعذر حذف المصدر' })
    }
  }, [refresh])

  const handleViewRuns = useCallback(async (id: number) => {
    if (runsForId === id) { setRunsForId(null); return }
    setRunsForId(id)
    setRunsLoading(true)
    try { setRuns(await getSyncRuns(id)) }
    catch { setRuns([]) }
    finally { setRunsLoading(false) }
  }, [runsForId])

  const handleViewChunks = useCallback(async (id: number) => {
    if (chunksForId === id) { setChunksForId(null); return }
    setChunksForId(id)
    setChunksLoading(true)
    setExpandedChunkIdx(null)
    try {
      const res = await getDynamicSourceChunks(id)
      setChunks(res.chunks)
      setChunksKey(res.chroma_key)
    } catch {
      setChunks([])
      setChunksKey('')
    } finally {
      setChunksLoading(false)
    }
  }, [chunksForId])

  const handleViewJobs = useCallback(async () => {
    setShowJobs(v => !v)
    if (showJobs) return
    setJobsLoading(true)
    try { const r = await getSchedulerJobs(); setJobs(r.jobs) }
    catch { setJobs([]) }
    finally { setJobsLoading(false) }
  }, [showJobs])

  return (
    <div className="space-y-6">

      {/* ── Tool-routing status ── */}
      <ToolRoutingStatusCard />

      {/* ── Form ── */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          {editingId !== null ? '✏️ تعديل مصدر البيانات' : '➕ إضافة مصدر بيانات جديد'}
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          أضف عنوان API الرسمي لجامعة الخليل هنا عند توفر بيانات الاعتماد. حتى ذلك الحين، أبقِ الحقل فارغاً
          وسيظهر المصدر بحالة «not_configured».
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">اسم المصدر</label>
            <input className="input" placeholder="مثال: التقويم الأكاديمي" value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          </div>
          <div>
            <label className="label">نوع المصدر</label>
            <select className="input" value={form.source_type}
              onChange={e => setForm(f => ({ ...f, source_type: e.target.value }))}>
              {SOURCE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className="label">عنوان API (اتركه فارغاً إذا لم يتوفر بعد)</label>
            <input className="input" placeholder="https://api.hebron.edu/calendar" value={form.endpoint_url}
              onChange={e => setForm(f => ({ ...f, endpoint_url: e.target.value }))} />
          </div>
          <div className="flex items-center gap-3 pt-5">
            <input type="checkbox" id="is_enabled" checked={form.is_enabled}
              onChange={e => setForm(f => ({ ...f, is_enabled: e.target.checked }))}
              className="w-4 h-4 text-primary rounded" />
            <label htmlFor="is_enabled" className="text-sm text-gray-700">مفعّل</label>
          </div>
          <div className="sm:col-span-2">
            <label className="label">
              رمز المصادقة (اختياري)
              {editingId !== null && form.auth_token && (
                <span className="mr-2 text-xs font-normal text-green-600">● محفوظ</span>
              )}
            </label>
            <input type="password" className="input"
              placeholder={
                editingId !== null
                  ? 'أدخل قيمة جديدة للتغيير، أو اتركه كما هو'
                  : 'مثال: hebron_api:test1234 أو Bearer token مباشر'
              }
              value={form.auth_token}
              onChange={e => setForm(f => ({ ...f, auth_token: e.target.value }))}
            />
            <p className="text-xs text-gray-400 mt-1">
              صيغة مدعومة: <code className="bg-gray-100 px-1 rounded">username:password</code> (يحصل على JWT تلقائياً) أو رمز Bearer مباشر.
            </p>
          </div>

          {/* Scheduling editor */}
          <div className="sm:col-span-2">
            <ScheduleEditor value={schedule} onChange={setSchedule} />
          </div>
        </div>

        {msg && (
          <div className={`mt-4 px-4 py-3 rounded-lg text-sm border ${
            msg.type === 'success' ? 'bg-green-50 text-green-800 border-green-200' : 'bg-red-50 text-red-800 border-red-200'
          }`}>{msg.text}</div>
        )}

        <div className="flex gap-3 mt-4 flex-wrap">
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? 'جاري الحفظ...' : editingId !== null ? '💾 حفظ التعديلات' : '➕ إضافة'}
          </button>
          {editingId !== null && (
            <button onClick={cancelEdit} className="btn-secondary">إلغاء</button>
          )}
        </div>
      </div>

      {/* ── Sources list ── */}
      <div className="card">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="text-lg font-semibold text-gray-800">📡 مصادر البيانات الحية</h2>
          <div className="flex gap-2">
            <button onClick={handleViewJobs} className="btn-secondary text-sm py-1.5 px-3">
              🕐 {showJobs ? 'إخفاء المهام' : 'عرض مهام الجدولة'}
            </button>
            <button onClick={refresh} className="btn-secondary text-sm py-1.5 px-3">🔄 تحديث</button>
          </div>
        </div>

        {/* Scheduler jobs panel */}
        {showJobs && (
          <div className="mb-4 border border-blue-200 rounded-xl bg-blue-50 p-4">
            <p className="text-sm font-semibold text-blue-800 mb-2">🕐 مهام الجدولة النشطة</p>
            {jobsLoading
              ? <p className="text-gray-500 text-sm">جاري جلب المهام...</p>
              : jobs.length === 0
                ? <p className="text-gray-400 text-sm">لا توجد مهام مجدولة حالياً. أضف مصدراً واختر نوع جدولة.</p>
                : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-right">
                      <thead>
                        <tr className="text-blue-700 border-b border-blue-200">
                          <th className="pb-1 pr-2">المصدر</th>
                          <th className="pb-1 pr-2">معرّف المهمة</th>
                          <th className="pb-1 pr-2">التشغيل القادم</th>
                          <th className="pb-1">التعبير الزمني</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-blue-100">
                        {jobs.map(j => (
                          <tr key={j.job_id} className="hover:bg-blue-100">
                            <td className="py-1.5 pr-2 font-medium text-gray-800">{j.source_name}</td>
                            <td className="py-1.5 pr-2 font-mono text-gray-500">{j.job_id}</td>
                            <td className="py-1.5 pr-2 text-gray-600">{j.next_run_time ? formatDate(j.next_run_time) : '—'}</td>
                            <td className="py-1.5 text-gray-500 font-mono">{j.trigger}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
          </div>
        )}

        {loading && <p className="text-gray-500 text-center py-8">جاري التحميل...</p>}
        {error   && <p className="text-red-600 text-center py-8">تعذر جلب المصادر.</p>}
        {!loading && !error && (sources ?? []).length === 0 && (
          <p className="text-gray-400 text-center py-8">لا توجد مصادر مضافة بعد.</p>
        )}

        <div className="space-y-3">
          {(sources ?? []).map(src => {
            const result = syncResult[src.id]
            return (
              <div key={src.id} className="border border-gray-200 rounded-xl bg-white overflow-hidden">
                {/* Header row */}
                <div className="p-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-800">{src.name}</span>
                      <span className="text-xs text-gray-500 bg-gray-100 rounded px-2 py-0.5">{src.source_type}</span>
                      {statusBadge(src.status)}
                      {!src.is_enabled && (
                        <span className="text-xs text-gray-400 border rounded px-2 py-0.5">معطّل</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-1 truncate">
                      {src.endpoint_url
                        ? `🔗 ${src.endpoint_url}`
                        : '⚠️ لم يُضَف عنوان API بعد — يتطلب إعداداً لبدء المزامنة'}
                    </p>
                    <p className="text-xs text-indigo-600 mt-0.5">📅 {scheduleLabel(src)}</p>
                    {src.last_sync_at && (
                      <p className="text-xs text-gray-400 mt-0.5">آخر مزامنة: {formatDate(src.last_sync_at)}</p>
                    )}
                    {src.error_message && (
                      <p className="text-xs text-red-600 mt-0.5 truncate">خطأ: {src.error_message}</p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button onClick={() => handleSync(src.id)} disabled={syncing === src.id}
                      className="btn-secondary text-xs py-1.5 px-3">
                      {syncing === src.id ? '⏳ جاري...' : '▶ مزامنة الآن'}
                    </button>
                    <button onClick={() => handleViewRuns(src.id)} className="btn-secondary text-xs py-1.5 px-3">
                      📋 السجل
                    </button>
                    <button onClick={() => handleViewChunks(src.id)} className="btn-secondary text-xs py-1.5 px-3">
                      🔍 عرض المقاطع
                    </button>
                    <button onClick={() => startEdit(src)} className="btn-secondary text-xs py-1.5 px-3">
                      ✏️ تعديل
                    </button>
                    <button onClick={() => setConfirmDelete(src.id)} className="btn-danger text-xs py-1.5 px-3">
                      🗑️ حذف
                    </button>
                  </div>
                </div>

                {/* Sync result inline */}
                {result && Object.keys(result).length > 0 && (
                  <div className={`border-t px-4 py-2 text-xs ${
                    result.ok ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
                  }`}>
                    {result.ok
                      ? `✅ نجحت المزامنة — تم جلب ${result.records_fetched} سجل، تحديث ${result.records_changed} منها، ${result.chunks_updated} مقطع في Chroma`
                      : `❌ ${result.error}`}
                  </div>
                )}

                {/* Confirm delete */}
                {confirmDelete === src.id && (
                  <div className="border-t bg-red-50 p-3">
                    <p className="text-sm text-red-800 mb-2">هل أنت متأكد من حذف هذا المصدر وسجل مزامناته؟</p>
                    <div className="flex gap-2">
                      <button onClick={() => handleDelete(src.id)} className="btn-danger text-sm py-1.5 px-3">نعم، احذف</button>
                      <button onClick={() => setConfirmDelete(null)} className="btn-secondary text-sm py-1.5 px-3">إلغاء</button>
                    </div>
                  </div>
                )}

                {/* Sync runs history */}
                {runsForId === src.id && (
                  <div className="border-t bg-gray-50 p-4">
                    <p className="text-xs font-semibold text-gray-600 mb-2">📋 سجل المزامنة</p>
                    {runsLoading
                      ? <p className="text-gray-500 text-sm">جاري جلب السجل...</p>
                      : runs.length === 0
                        ? <p className="text-gray-400 text-sm">لا يوجد سجل مزامنة بعد.</p>
                        : (
                          <div className="space-y-2 max-h-64 overflow-y-auto">
                            {runs.map(run => (
                              <div key={run.id} className="bg-white border border-gray-200 rounded-lg p-3 text-xs">
                                <div className="flex items-center gap-2 mb-1">
                                  {statusBadge(run.status)}
                                  <span className="text-gray-500">{formatDate(run.started_at)}</span>
                                </div>
                                <p className="text-gray-600">
                                  جُلب: {run.records_fetched} · تغيّر: {run.records_changed} · مقاطع: {run.chunks_updated}
                                </p>
                                {run.error_message && (
                                  <p className="text-red-600 mt-1">{run.error_message}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                  </div>
                )}

                {/* Chroma chunks */}
                {chunksForId === src.id && (
                  <div className="border-t bg-gray-50 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs font-semibold text-gray-600">
                        🗂️ المقاطع الحالية في Chroma
                        {!chunksLoading && (
                          <span className="mr-2 text-gray-400 font-normal">
                            ({chunks.length} مقطع · المفتاح: <code className="bg-gray-200 px-1 rounded">{chunksKey}</code>)
                          </span>
                        )}
                      </p>
                    </div>
                    {chunksLoading
                      ? <p className="text-gray-500 text-sm">جاري جلب المقاطع...</p>
                      : chunks.length === 0
                        ? <p className="text-gray-400 text-sm">لا توجد مقاطع مفهرسة لهذا المصدر. قم بالمزامنة أولاً.</p>
                        : (
                          <div className="space-y-2 max-h-96 overflow-y-auto">
                            {chunks.map((chunk, idx) => (
                              <div key={idx} className="bg-white border border-gray-200 rounded-lg overflow-hidden text-xs">
                                <button
                                  onClick={() => setExpandedChunkIdx(expandedChunkIdx === idx ? null : idx)}
                                  className="w-full text-right p-3 flex items-start justify-between hover:bg-gray-50 transition-colors gap-2"
                                >
                                  <span className="text-gray-700 line-clamp-2 flex-1">
                                    {chunk.page_content.slice(0, 120)}{chunk.page_content.length > 120 ? '...' : ''}
                                  </span>
                                  <span className="text-gray-400 flex-shrink-0">{expandedChunkIdx === idx ? '▼' : '◀'}</span>
                                </button>
                                {expandedChunkIdx === idx && (
                                  <div className="border-t border-gray-100 p-3 space-y-2">
                                    <p className="text-gray-800 whitespace-pre-wrap leading-relaxed">{chunk.page_content}</p>
                                    {Object.keys(chunk.metadata).length > 0 && (
                                      <div className="bg-gray-50 rounded p-2 space-y-0.5">
                                        <p className="text-gray-500 font-medium mb-1">البيانات الوصفية:</p>
                                        {Object.entries(chunk.metadata).map(([k, v]) => (
                                          <p key={k} className="text-gray-500">
                                            <span className="font-medium text-gray-600">{k}:</span> {String(v)}
                                          </p>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Info box ── */}
      <div className="card bg-blue-50 border-blue-200">
        <h3 className="font-semibold text-blue-900 mb-2">ℹ️ كيفية إعداد مصدر بيانات</h3>
        <ol className="text-sm text-blue-800 space-y-1 list-decimal list-inside">
          <li>أضف مصدراً جديداً باختيار النوع المناسب.</li>
          <li>اتركه بدون عنوان URL حتى تحصل على بيانات API من فريق IT بالجامعة.</li>
          <li>عند توفر عنوان API، عدّل المصدر وأضفه، ثم اضغط «مزامنة الآن».</li>
          <li>اختر نوع الجدولة (يومياً / أسبوعياً / شهرياً) وأضف الأوقات المطلوبة لتشغيل المزامنة تلقائياً.</li>
          <li>بعد المزامنة الناجحة، تبدأ بيانات التقويم والإعلانات بالظهور في إجابات الشات بوت.</li>
        </ol>
      </div>
    </div>
  )
}
