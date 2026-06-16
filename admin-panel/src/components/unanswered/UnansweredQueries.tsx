import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  Clock,
  HelpCircle,
  Loader2,
  PartyPopper,
  Puzzle,
  RefreshCw,
} from 'lucide-react'
import { IconHeading, IconText } from '../ui/IconText'
import { listUnanswered, resolveQuery, resolveAllQueries } from '../../api/unanswered'
import { useData } from '../../hooks/useData'

function formatTime(ts: string): string {
  if (!ts) return '—'
  const safeTs = ts.includes('Z') || ts.includes('+') ? ts : ts.replace(' ', 'T') + 'Z'
  try { return new Date(safeTs).toLocaleString('ar-SA', { timeZone: 'Asia/Hebron' }) } catch { return ts }
}

const REASON_LABELS: Record<string, { label: string; color: string }> = {
  'لا يوجد سياق مطابق في قاعدة البيانات': { label: 'لا سياق', color: 'badge-warning' },
  'السؤال ليس بالعربية أو الإنجليزية': { label: 'لغة غير مدعومة', color: 'badge-gray' },
  'السؤال خارج نطاق جامعة الخليل أو لا يتعلق بخدماتها': { label: 'خارج النطاق', color: 'badge-danger' },
  'النموذج لم يتمكن من استخراج الإجابة من السياق': { label: 'فشل النموذج', color: 'badge-danger' },
}

function previewLine(text: string, max = 72): string {
  const t = text.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max)}…`
}

function reasonDisplay(reason: string): string {
  return REASON_LABELS[reason]?.label ?? reason
}

export default function UnansweredQueries() {
  const { data: queries, loading, error, refresh } = useData(listUnanswered)
  const [resolving, setResolving] = useState<number | null>(null)
  const [bulkResolving, setBulkResolving] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [reasonFilter, setReasonFilter] = useState<string>('all')

  const distinctReasons = useMemo(() => {
    const u = [...new Set((queries ?? []).map((q) => q.reason))]
    u.sort((a, b) => a.localeCompare(b, 'ar'))
    return u
  }, [queries])

  const filtered = useMemo(() => {
    if (!queries) return []
    if (reasonFilter === 'all') return queries
    return queries.filter((q) => q.reason === reasonFilter)
  }, [queries, reasonFilter])

  const handleResolve = async (id: number) => {
    setResolving(id)
    try {
      await resolveQuery(id)
      refresh()
    } catch {
      alert('تعذر تحديث حالة السؤال')
    } finally {
      setResolving(null)
    }
  }

  const handleResolveAll = async () => {
    if (!queries?.length || filtered.length === 0) return
    const confirmMsg =
      reasonFilter === 'all'
        ? 'سيتم تعليم جميع الأسئلة غير المجابة المعلّقة كمحلولة. لا يمكن التراجع. متابعة؟'
        : `سيتم تعليم جميع الأسئلة المعلّقة ذات السبب «${reasonDisplay(reasonFilter)}» كمحلولة. لا يمكن التراجع. متابعة؟`
    if (!window.confirm(confirmMsg)) return
    setBulkResolving(true)
    try {
      const { resolved } = await resolveAllQueries(reasonFilter === 'all' ? null : reasonFilter)
      await refresh()
      setExpandedId(null)
      alert(`تم تعليم ${resolved} سجل/سجلات كمحلولة.`)
    } catch {
      alert('تعذر تنفيذ التعليم الجماعي.')
    } finally {
      setBulkResolving(false)
    }
  }

  const showCelebration = !loading && !error && (queries?.length === 0)
  const showFilteredEmpty =
    !loading && !error && (queries?.length ?? 0) > 0 && filtered.length === 0

  return (
    <div className="card">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-4">
        <div>
          <IconHeading icon={Puzzle} className="text-lg font-semibold text-gray-800">
            الأسئلة غير المجابة
          </IconHeading>
          <p className="text-sm text-gray-500 mt-0.5">أسئلة لم يتمكن الروبوت من الإجابة عليها بدقة.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-end">
          <button
            type="button"
            onClick={handleResolveAll}
            disabled={
              bulkResolving || !queries?.length || loading || filtered.length === 0
            }
            className="btn-primary text-sm py-2 px-4 whitespace-nowrap shadow-sm flex-shrink-0 inline-flex items-center gap-1.5"
          >
            {bulkResolving ? (
              <IconText icon={Loader2} iconClassName="w-4 h-4 shrink-0 animate-spin">جاري التحديث...</IconText>
            ) : (
              <IconText icon={CheckCircle2}>تعليم الكل كمحلول</IconText>
            )}
          </button>
          <button onClick={refresh} className="btn-secondary text-sm py-2 px-4 flex-shrink-0 inline-flex items-center gap-1.5" disabled={bulkResolving}>
            <RefreshCw className="w-4 h-4 shrink-0" aria-hidden="true" />
            تحديث
          </button>
        </div>
      </div>

      {!loading && !error && (queries?.length ?? 0) > 0 && (
        <div className="mb-5 pb-4 border-b border-gray-100">
          <div className="max-w-xl">
            <label className="label text-xs mb-1 block text-gray-700">تصفية حسب سبب الفشل</label>
            <select
              className="input text-sm w-full"
              value={reasonFilter}
              onChange={(e) => {
                setReasonFilter(e.target.value)
                setExpandedId(null)
              }}
              disabled={bulkResolving}
            >
              <option value="all">كل الأسباب ({queries?.length ?? 0})</option>
              {distinctReasons.map((r) => (
                <option key={r} value={r}>
                  {reasonDisplay(r)} ({(queries ?? []).filter((q) => q.reason === r).length})
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-2 leading-relaxed">
              {reasonFilter === 'all'
                ? '«تعليم الكل كمحلول» يشمل كل الأسئلة المعلّقة حالياً.'
                : '«تعليم الكل كمحلول» يشمل الأسئلة المعلّقة لهذا السبب فقط.'}
            </p>
          </div>
        </div>
      )}

      {loading && <p className="text-gray-500 text-center py-8">جاري التحميل...</p>}
      {error && <p className="text-red-600 text-center py-4">تعذر جلب البيانات.</p>}

      {showCelebration && (
        <div className="text-center py-10">
          <PartyPopper className="w-10 h-10 mx-auto mb-3 text-green-600" aria-hidden="true" />
          <p className="text-green-700 font-medium">لا توجد أسئلة غير مجابة! الروبوت يجيب على كل شيء.</p>
        </div>
      )}

      {showFilteredEmpty && (
        <div className="text-center py-8 border border-dashed border-gray-200 rounded-lg bg-gray-50">
          <p className="text-gray-600">لا توجد أسئلة تطابق سبب الفشل المحدد.</p>
          <button type="button" className="text-sm text-primary mt-2 underline" onClick={() => setReasonFilter('all')}>
            عرض كل الأسباب
          </button>
        </div>
      )}

      <div className="space-y-2">
        {filtered.map((q) => {
          const reasonInfo = REASON_LABELS[q.reason] ?? { label: q.reason, color: 'badge-gray' }
          const isOpen = expandedId === q.id
          return (
            <div key={q.id} className="border rounded-lg overflow-hidden bg-white border-gray-200">
              <button
                type="button"
                onClick={() => setExpandedId(isOpen ? null : q.id)}
                className="w-full text-right p-4 flex items-center justify-between gap-3 hover:bg-gray-50 transition-colors"
              >
                <div className="flex-1 min-w-0 text-right">
                  <p className="font-medium text-gray-800 text-sm truncate">
                    ❓ {previewLine(q.question, 90)}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 mt-1 justify-end">
                    <span className={reasonInfo.color}>⚠️ {reasonInfo.label}</span>
                  </div>
                </div>
                <span className="text-gray-400 flex-shrink-0 mr-2">{isOpen ? '▼' : '◀'}</span>
              </button>
              {isOpen && (
                <div className="border-t border-gray-100 bg-gray-50 p-4 space-y-3">
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1">السؤال كاملاً</p>
                    <p className="text-sm text-gray-800 whitespace-pre-wrap break-words">{q.question}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                    <span className={reasonInfo.color}>⚠️ {reasonInfo.label}</span>
                    <span>🕒 {formatTime(q.timestamp)}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleResolve(q.id)}
                    disabled={resolving === q.id || bulkResolving}
                    className="btn-primary text-sm py-2 px-4"
                  >
                    {resolving === q.id ? '...' : '✅ محلول'}
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
