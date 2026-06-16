import { useState, useCallback, useRef } from 'react'
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  ClipboardList,
  FileText,
  Loader2,
  RefreshCw,
} from 'lucide-react'
import { IconHeading, IconText } from '../ui/IconText'
import {
  getStaleFiles,
  markFileReviewed,
  replaceFile,
  retireFile,
  getFileVersions,
  StaleFile,
  DocumentVersion,
} from '../../api/fileLifecycle'
import { useData } from '../../hooks/useData'

function reasonLabel(r: string) {
  const map: Record<string, string> = {
    stale: 'حالة: قديم',
    retired: 'حالة: متقاعد',
    past_valid_until: 'انتهى تاريخ الصلاحية',
    review_overdue: 'التحقق متأخر',
  }
  return map[r] ?? r
}

export default function StaleDocuments() {
  const { data: files, loading, error, refresh } = useData(getStaleFiles)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [versions, setVersions] = useState<DocumentVersion[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [reviewingId, setReviewingId] = useState<number | null>(null)
  const [replacingId, setReplacingId] = useState<number | null>(null)
  const [msg, setMsg] = useState<{ id: number; type: 'success' | 'error'; text: string } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const formatDate = (d: string | null) => {
    if (!d) return '—'
    try {
      return new Date(d).toLocaleDateString('ar-SA', { timeZone: 'Asia/Hebron' })
    } catch {
      return d
    }
  }

  const handleExpand = useCallback(async (file: StaleFile) => {
    if (expandedId === file.id) { setExpandedId(null); return }
    setExpandedId(file.id)
    setVersionsLoading(true)
    try {
      const v = await getFileVersions(file.id)
      setVersions(v)
    } catch {
      setVersions([])
    } finally {
      setVersionsLoading(false)
    }
  }, [expandedId])

  const handleReview = useCallback(async (file: StaleFile) => {
    setReviewingId(file.id)
    try {
      await markFileReviewed(file.id)
      setMsg({ id: file.id, type: 'success', text: 'تم تحديث حالة المستند إلى "نشط".' })
      refresh()
    } catch {
      setMsg({ id: file.id, type: 'error', text: 'تعذر تحديث الحالة.' })
    } finally {
      setReviewingId(null)
    }
  }, [refresh])

  const handleReplace = useCallback(async (file: StaleFile, newFile: File) => {
    setReplacingId(file.id)
    setMsg(null)
    try {
      const result = await replaceFile(file.id, newFile)
      setMsg({ id: file.id, type: 'success', text: `تم الاستبدال بنجاح: ${result.original_filename} — ${result.chunks} مقطع` })
      refresh()
    } catch (e: unknown) {
      const err = (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'فشل الاستبدال'
      setMsg({ id: file.id, type: 'error', text: err })
    } finally {
      setReplacingId(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }, [refresh])

  const handleRetire = useCallback(async (file: StaleFile) => {
    try {
      await retireFile(file.id)
      refresh()
    } catch {
      setMsg({ id: file.id, type: 'error', text: 'تعذر تقاعد الملف.' })
    }
  }, [refresh])

  return (
    <div className="space-y-5">
      <div className="card bg-amber-50 border-amber-200">
        <IconHeading as="h3" icon={AlertTriangle} className="font-semibold text-amber-900 mb-1">
          المستندات القديمة أو التي تحتاج إلى مراجعة
        </IconHeading>
        <p className="text-sm text-amber-800">
          هذه المستندات تجاوزت تاريخ صلاحيتها، أو تجاوزت موعد المراجعة، أو حالتها «قديم». راجعها
          واستبدلها أو قم بتأكيدها إذا لا تزال صحيحة.
        </p>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <IconHeading icon={ClipboardList} className="text-lg font-semibold text-gray-800">
            المستندات التي تحتاج انتباهاً
          </IconHeading>
          <button onClick={refresh} className="btn-secondary text-sm py-1.5 px-3 inline-flex items-center gap-1.5">
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            تحديث
          </button>
        </div>

        {loading && <p className="text-gray-500 text-center py-8">جاري التحميل...</p>}
        {error && <p className="text-red-600 text-center py-8">تعذر جلب البيانات.</p>}
        {!loading && !error && (files ?? []).length === 0 && (
          <p className="text-green-700 text-center py-8 font-medium inline-flex items-center justify-center gap-2 w-full">
            <CheckCircle2 className="w-5 h-5 shrink-0" aria-hidden="true" />
            جميع المستندات محدّثة — لا توجد ملفات تحتاج انتباهاً.
          </p>
        )}

        <div className="space-y-3">
          {(files ?? []).map((file) => (
            <div key={file.id} className="border border-amber-200 rounded-xl bg-white overflow-hidden">
              {/* Header */}
              <button
                onClick={() => handleExpand(file)}
                className="w-full text-right p-4 flex items-center justify-between hover:bg-amber-50 transition-colors"
              >
                <div className="flex-1 min-w-0 text-right">
                  <p className="font-medium text-gray-800 truncate inline-flex items-center gap-1.5 max-w-full">
                    <FileText className="w-4 h-4 shrink-0 text-gray-500" aria-hidden="true" />
                    <span className="truncate">{file.original_filename}</span>
                  </p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {file.reasons.map((r) => (
                      <span key={r} className="text-xs bg-amber-100 text-amber-800 border border-amber-200 px-2 py-0.5 rounded-full">
                        {reasonLabel(r)}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {file.valid_until && `صالح حتى: ${formatDate(file.valid_until)} · `}
                    {file.next_review_at && `مراجعة بحلول: ${formatDate(file.next_review_at)}`}
                  </p>
                </div>
                <span className="text-gray-400 flex-shrink-0 mr-3">{expandedId === file.id ? '▼' : '◀'}</span>
              </button>

              {/* Expanded actions */}
              {expandedId === file.id && (
                <div className="border-t border-amber-100 bg-amber-50 p-4 space-y-3">
                  {msg?.id === file.id && (
                    <div className={`px-3 py-2 rounded text-sm ${
                      msg.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'
                    }`}>{msg.text}</div>
                  )}

                  <div className="flex flex-wrap gap-2">
                    {/* Mark reviewed — not applicable for retired files */}
                    {file.status !== 'retired' && (
                      <button
                        onClick={() => handleReview(file)}
                        disabled={reviewingId === file.id}
                        className="btn-secondary text-sm py-2 px-4 inline-flex items-center gap-1.5"
                      >
                        {reviewingId === file.id ? '...' : <IconText icon={CheckCircle2}>تأكيد صحة المستند</IconText>}
                      </button>
                    )}

                    {/* Replace file */}
                    <label className="btn-primary text-sm py-2 px-4 cursor-pointer flex items-center gap-1">
                      {replacingId === file.id ? (
                        <IconText icon={Loader2} iconClassName="w-4 h-4 shrink-0 animate-spin">جاري الاستبدال...</IconText>
                      ) : (
                        <IconText icon={RefreshCw}>استبدال الملف</IconText>
                      )}
                      <input
                        ref={fileInputRef}
                        type="file"
                        className="hidden"
                        accept=".pdf,.docx,.txt,.csv,.xlsx,.xls,.json"
                        disabled={replacingId === file.id}
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) handleReplace(file, f)
                        }}
                      />
                    </label>

                    {/* Retire */}
                    {file.status !== 'retired' && (
                      <button onClick={() => handleRetire(file)} className="btn-danger text-sm py-2 px-4 inline-flex items-center gap-1.5">
                        <IconText icon={Archive}>تقاعد المستند</IconText>
                      </button>
                    )}
                  </div>

                  {/* Audit trail */}
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">سجل الإصدارات</p>
                    {versionsLoading
                      ? <p className="text-gray-500 text-xs">جاري التحميل...</p>
                      : versions.length === 0
                        ? <p className="text-gray-400 text-xs">لا يوجد سجل إصدارات.</p>
                        : (
                          <div className="space-y-1 max-h-48 overflow-y-auto">
                            {versions.map((v) => (
                              <div key={v.id} className="bg-white border border-gray-200 rounded p-2 text-xs text-gray-700">
                                <span className="font-medium">v{v.version_number}</span>
                                {' · '}
                                <span className="text-gray-500">{v.action}</span>
                                {' · '}
                                <span>{new Date(v.created_at ?? '').toLocaleString('ar-SA')}</span>
                                {v.note && <span className="text-gray-400 block mt-0.5">{v.note}</span>}
                              </div>
                            ))}
                          </div>
                        )
                    }
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
