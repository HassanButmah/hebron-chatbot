import { useState, useCallback, useRef } from 'react'
import {
  Archive,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ClipboardList,
  Download,
  FileText,
  FolderOpen,
  Loader2,
  Recycle,
  RefreshCw,
  Save,
  Search,
  Trash2,
  XCircle,
} from 'lucide-react'
import { IconHeading, IconText } from '../ui/IconText'
import { listFiles, uploadFile, deleteFile, getFileChunks, downloadUrl, FileRecord, Chunk } from '../../api/files'
import { updateFileFreshness, markFileReviewed, retireFile, restoreFile, reindexFile } from '../../api/fileLifecycle'
import { useData } from '../../hooks/useData'

type SortOption = 'newest' | 'oldest' | 'name_asc' | 'name_desc' | 'chunks_desc' | 'chunks_asc'

const SORT_LABELS: Record<SortOption, string> = {
  newest: 'الأحدث أولاً',
  oldest: 'الأقدم أولاً',
  name_asc: 'حسب الاسم (أ–ي)',
  name_desc: 'حسب الاسم (ي–أ)',
  chunks_desc: 'الأكثر مقاطعاً أولاً',
  chunks_asc: 'الأقل مقاطعاً أولاً',
}

function sortFiles(files: FileRecord[], sort: SortOption): FileRecord[] {
  const list = [...files]
  const toDate = (d: string | null) => (d ? new Date(d).getTime() : 0)
  switch (sort) {
    case 'newest': return list.sort((a, b) => toDate(b.upload_date) - toDate(a.upload_date))
    case 'oldest': return list.sort((a, b) => toDate(a.upload_date) - toDate(b.upload_date))
    case 'name_asc': return list.sort((a, b) => a.original_filename.localeCompare(b.original_filename))
    case 'name_desc': return list.sort((a, b) => b.original_filename.localeCompare(a.original_filename))
    case 'chunks_desc': return list.sort((a, b) => b.chunk_count - a.chunk_count)
    case 'chunks_asc': return list.sort((a, b) => a.chunk_count - b.chunk_count)
  }
}

/** Matches backend `get_stale_files`: would appear in tab «مستندات تحتاج مراجعة». */
function parseUtcMs(ts: string): number {
  const safe = ts.includes('Z') || ts.includes('+') ? ts : ts.replace(' ', 'T') + 'Z'
  const ms = new Date(safe).getTime()
  return Number.isNaN(ms) ? NaN : ms
}

function fileAppearsInStaleTab(file: FileRecord): boolean {
  const reasons: string[] = []
  if (file.status === 'stale' || file.status === 'retired') reasons.push(file.status)
  const now = Date.now()
  const vuMs = file.valid_until ? parseUtcMs(file.valid_until) : NaN
  const nrMs = file.next_review_at ? parseUtcMs(file.next_review_at) : NaN
  if (!Number.isNaN(vuMs) && vuMs < now) reasons.push('past_valid_until')
  if (!Number.isNaN(nrMs) && nrMs < now) reasons.push('review_overdue')
  return reasons.length > 0
}

/** Returns days until valid_until. Negative means expired. Null means no date set. */
function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const diff = new Date(dateStr).getTime() - Date.now()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function ValidityBadge({ file }: { file: FileRecord }) {
  if (file.status === 'indexing') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border bg-blue-100 text-blue-700 border-blue-200 animate-pulse">
        <Loader2 className="w-3 h-3 shrink-0 animate-spin" aria-hidden="true" />
        جاري الفهرسة
      </span>
    )
  }
  if (file.status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border bg-red-100 text-red-700 border-red-200">
        <XCircle className="w-3 h-3 shrink-0" aria-hidden="true" />
        فشل الفهرسة
      </span>
    )
  }
  if (file.status === 'retired') {
    return <span className="text-xs font-medium px-2 py-0.5 rounded-full border bg-gray-100 text-gray-500 border-gray-200">متقاعد</span>
  }
  const days = daysUntil(file.valid_until)
  if (days === null) {
    return <span className="text-xs font-medium px-2 py-0.5 rounded-full border bg-gray-100 text-gray-500 border-gray-200">بدون تاريخ صلاحية</span>
  }
  if (days < 0) {
    return <span className="text-xs font-medium px-2 py-0.5 rounded-full border bg-red-100 text-red-700 border-red-200">منتهي الصلاحية</span>
  }
  if (days <= 30) {
    return <span className="text-xs font-medium px-2 py-0.5 rounded-full border bg-amber-100 text-amber-700 border-amber-200">ينتهي خلال {days} يوم</span>
  }
  return <span className="text-xs font-medium px-2 py-0.5 rounded-full border bg-green-100 text-green-700 border-green-200">صالح {days} يوم</span>
}

/** Convert a stored ISO string to a local date input value (YYYY-MM-DD) */
function isoToDateInput(iso: string | null): string {
  if (!iso) return ''
  try { return new Date(iso).toISOString().slice(0, 10) } catch { return '' }
}

export default function FileManager() {
  const { data: files, loading, error, refresh } = useData(listFiles)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [deleteMsg, setDeleteMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortOption>('newest')
  const [expandedFileId, setExpandedFileId] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [viewChunksFor, setViewChunksFor] = useState<string | null>(null)
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [chunksLoading, setChunksLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Freshness edit state: id of the file whose panel is open
  const [editFreshnessId, setEditFreshnessId] = useState<number | null>(null)
  const [freshnessForm, setFreshnessForm] = useState({
    valid_until: '',
    next_review_at: '',
    owner: '',
    category: '',
    source_url: '',
  })
  const [savingFreshness, setSavingFreshness] = useState(false)
  const [freshnessMsg, setFreshnessMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [confirmRetireId, setConfirmRetireId] = useState<number | null>(null)
  const [retiring, setRetiring] = useState(false)
  const [restoringId, setRestoringId] = useState<number | null>(null)
  const [reindexingId, setReindexingId] = useState<number | null>(null)

  const handleUpload = useCallback(async (file: File) => {
    setUploading(true)
    setUploadMsg(null)
    try {
      const data = await uploadFile(file)
      // Detect silent rename: stored name differs from what the user chose
      const wasDuplicate = data.filename !== file.name && data.filename !== data.original_filename
      const renamedNote = wasDuplicate
        ? ` (اسم الملف كان موجوداً مسبقاً، تم حفظه باسم "${data.filename}")`
        : ''
      setUploadMsg({
        type: 'success',
        text: `تم رفع الملف بنجاح: ${data.original_filename} — ${data.chunks} مقطع. صالح لمدة 6 أشهر افتراضياً.${renamedNote}`,
      })
      refresh()
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (e: unknown) {
      const errData = (e as { response?: { data?: { error?: string; hint?: string } } })?.response?.data
      const msg = errData?.error || 'فشل رفع الملف'
      const hint = errData?.hint ? ` — ${errData.hint}` : ''
      setUploadMsg({ type: 'error', text: msg + hint })
      // Always refresh: a 'failed' DB record may have been created and needs to be visible
      refresh()
      if (fileInputRef.current) fileInputRef.current.value = ''
    } finally {
      setUploading(false)
    }
  }, [refresh])

  const handleDeleteConfirm = async () => {
    if (!confirmDelete) return
    const deletedName = confirmDelete
    try {
      await deleteFile(deletedName)
      setConfirmDelete(null)
      setViewChunksFor(null)
      setExpandedFileId(null)
      setDeleteMsg({ type: 'success', text: `تم حذف الملف "${deletedName}" بنجاح.` })
      refresh()
    } catch {
      setDeleteMsg({ type: 'error', text: 'تعذر حذف الملف.' })
    }
  }

  const openFreshnessEdit = (file: FileRecord) => {
    setEditFreshnessId(file.id)
    setFreshnessForm({
      valid_until: isoToDateInput(file.valid_until),
      next_review_at: isoToDateInput(file.next_review_at),
      owner: file.owner ?? '',
      category: file.category ?? '',
      source_url: file.source_url ?? '',
    })
    setFreshnessMsg(null)
  }

  const handleSaveFreshness = async (fileId: number) => {
    setSavingFreshness(true)
    setFreshnessMsg(null)
    try {
      await updateFileFreshness(fileId, {
        valid_until: freshnessForm.valid_until ? freshnessForm.valid_until + 'T00:00:00Z' : undefined,
        next_review_at: freshnessForm.next_review_at ? freshnessForm.next_review_at + 'T00:00:00Z' : undefined,
        owner: freshnessForm.owner || undefined,
        category: freshnessForm.category || undefined,
        source_url: freshnessForm.source_url.trim(),
      })
      setFreshnessMsg({ type: 'success', text: 'تم حفظ معلومات الملف.' })
      refresh()
    } catch {
      setFreshnessMsg({ type: 'error', text: 'تعذر حفظ البيانات.' })
    } finally {
      setSavingFreshness(false)
    }
  }

  const handleMarkReviewed = async (fileId: number) => {
    try {
      await markFileReviewed(fileId)
      refresh()
    } catch {
      alert('تعذر تحديث حالة المراجعة.')
    }
  }

  const handleRetireConfirm = async (fileId: number) => {
    setRetiring(true)
    try {
      await retireFile(fileId)
      setConfirmRetireId(null)
      refresh()
    } catch {
      alert('تعذر تقاعد الملف.')
    } finally {
      setRetiring(false)
    }
  }

  const handleRestore = async (fileId: number) => {
    setRestoringId(fileId)
    try {
      const res = await restoreFile(fileId)
      setUploadMsg({ type: 'success', text: `تمت استعادة الملف "${res.filename}" بنجاح — ${res.chunk_count} مقطع.` })
      refresh()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error || 'تعذر استعادة الملف.'
      setUploadMsg({ type: 'error', text: msg })
    } finally {
      setRestoringId(null)
    }
  }

  const handleReindex = async (fileId: number) => {
    setReindexingId(fileId)
    try {
      const res = await reindexFile(fileId)
      setUploadMsg({ type: 'success', text: `تمت إعادة فهرسة "${res.filename}" بنجاح — ${res.chunk_count} مقطع.` })
      refresh()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error || 'تعذر إعادة الفهرسة.'
      setUploadMsg({ type: 'error', text: msg })
    } finally {
      setReindexingId(null)
    }
  }

  const handleViewChunks = async (filename: string) => {
    if (viewChunksFor === filename) { 
      setViewChunksFor(null)
      return 
    }
    setViewChunksFor(filename)
    setChunksLoading(true)
    try {
      const c = await getFileChunks(filename)
      setChunks(c)
    } catch {
      setChunks([])
    } finally {
      setChunksLoading(false)
    }
  }

  const q = search.trim().toLowerCase()
  const filtered = sortFiles(
    (files ?? []).filter((f) =>
      !q || f.original_filename.toLowerCase().includes(q) || f.filename.toLowerCase().includes(q)
    ),
    sort
  )

  const formatDate = (d: string | null) => {
    if (!d) return '—'
    const safeD = d.includes('Z') || d.includes('+') ? d : d.replace(' ', 'T') + 'Z'
    try {
      const dt = new Date(safeD)
      const zone = 'Asia/Hebron'
      const datePart = dt.toLocaleDateString('ar-SA', {
        timeZone: zone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      })
      const timePart = dt.toLocaleTimeString('ar-SA', {
        timeZone: zone,
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      })
      return `${datePart} - ${timePart}`
    } catch {
      return d
    }
  }

  return (
    <div className="space-y-6">
      {/* Upload section */}
      <div className="card">
        <IconHeading icon={FolderOpen} className="text-lg font-semibold text-gray-800 mb-4">
          رفع مستند جديد
        </IconHeading>
        <p className="text-sm text-gray-500 mb-3">
          الأنواع المدعومة: PDF، TXT، CSV، Excel (xlsx/xls)، JSON
        </p>
        <div className="flex items-center gap-3 flex-wrap">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.csv,.xlsx,.xls,.json"
            className="block w-full text-sm text-gray-500 file:ml-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:font-medium file:bg-primary file:text-white hover:file:bg-primary-light"
            disabled={uploading}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleUpload(file)
            }}
          />
          {uploading && <span className="text-sm text-gray-500 animate-pulse">جاري الرفع...</span>}
        </div>
        {uploadMsg && (
          <div className={`mt-3 px-4 py-3 rounded-lg text-sm ${
            uploadMsg.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'
          }`}>
            {uploadMsg.text}
          </div>
        )}
        {deleteMsg && (
          <div className={`mt-3 px-4 py-3 rounded-lg text-sm ${
            deleteMsg.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'
          }`}>
            {deleteMsg.text}
          </div>
        )}
      </div>

      {/* File list */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <IconHeading icon={ClipboardList} className="text-lg font-semibold text-gray-800">
            الملفات المحملة
          </IconHeading>
          <button onClick={refresh} className="btn-secondary text-sm py-1.5 px-3 inline-flex items-center gap-1.5">
            <RefreshCw className="w-4 h-4 shrink-0" aria-hidden="true" />
            تحديث
          </button>
        </div>

        {/* Search & sort */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          <div className="relative">
            <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" aria-hidden="true" />
            <input
              type="text"
              className="input text-sm pr-9"
              placeholder="بحث عن ملف..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div>
            <select className="input text-sm" value={sort} onChange={(e) => setSort(e.target.value as SortOption)}>
              {(Object.keys(SORT_LABELS) as SortOption[]).map((k) => (
                <option key={k} value={k}>{SORT_LABELS[k]}</option>
              ))}
            </select>
          </div>
        </div>

        {loading && <p className="text-gray-500 text-center py-8">جاري التحميل...</p>}
        {error && <p className="text-red-600 text-center py-8">تعذر جلب الملفات. تأكد من تشغيل الخادم.</p>}
        {!loading && !error && filtered.length === 0 && (
          <p className="text-gray-400 text-center py-8">لا توجد ملفات محملة بعد.</p>
        )}

        <div className="space-y-2">
          {filtered.map((file) => {
            const isExpanded = expandedFileId === file.filename
            const isDeleting = confirmDelete === file.filename
            const isEditingFreshness = editFreshnessId === file.id
            const isConfirmingRetire = confirmRetireId === file.id
            const isRetired = file.status === 'retired'
            const isFailed = file.status === 'failed' || file.status === 'indexing'
            return (
              <div key={file.id} className={`border rounded-lg overflow-hidden bg-white ${isRetired ? 'border-gray-300 opacity-70' : 'border-gray-200'}`}>
                {/* Accordion header */}
                <button
                  onClick={() => setExpandedFileId(isExpanded ? null : file.filename)}
                  className="w-full text-right p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
                >
                  <div className="flex-1 min-w-0 text-right">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium text-gray-800 truncate inline-flex items-center gap-1.5 min-w-0">
                        <FileText className="w-4 h-4 shrink-0 text-gray-500" aria-hidden="true" />
                        <span className="truncate">{file.original_filename}</span>
                      </p>
                      <ValidityBadge file={file} />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center justify-start gap-x-1.5 sm:gap-x-2 gap-y-1.5 text-xs text-gray-600 leading-relaxed">
                      <span>{file.chunk_count} مقطع</span>
                      <span>{formatDate(file.upload_date)}</span>
                      {file.valid_until ? (
                        <span>صالح حتى: {formatDate(file.valid_until)}</span>
                      ) : null}
                    </div>
                  </div>
                  <span className="text-gray-400 flex-shrink-0 mr-3">
                    {isExpanded
                      ? <ChevronDown className="w-4 h-4" aria-hidden="true" />
                      : <ChevronLeft className="w-4 h-4" aria-hidden="true" />}
                  </span>
                </button>

                {/* Expanded content */}
                {isExpanded && (
                  <div className="border-t border-gray-100 bg-gray-50 p-4 space-y-3">
                    <div className="flex flex-wrap gap-2 items-center">
                      <a
                        href={downloadUrl(file.filename)}
                        className="btn-secondary text-sm py-2 px-4 flex items-center gap-2"
                        download
                      >
                        <IconText icon={Download}>تنزيل</IconText>
                      </a>
                      <button
                        onClick={() => handleViewChunks(file.filename)}
                        className="btn-secondary text-sm py-2 px-4 inline-flex items-center gap-1.5"
                      >
                        <IconText icon={Search}>عرض المقاطع</IconText>
                      </button>
                      {!isRetired && (
                        <button
                          onClick={() => isEditingFreshness ? setEditFreshnessId(null) : openFreshnessEdit(file)}
                          className="btn-secondary text-sm py-2 px-4 inline-flex items-center gap-1.5"
                        >
                          <IconText icon={ClipboardList}>{isEditingFreshness ? 'إغلاق معلومات الملف' : 'تعديل معلومات الملف'}</IconText>
                        </button>
                      )}
                      {fileAppearsInStaleTab(file) && !isRetired && (
                        <button
                          onClick={() => handleMarkReviewed(file.id)}
                          className="btn-secondary text-sm py-2 px-4 inline-flex items-center gap-1.5"
                        >
                          <IconText icon={CheckCircle2}>تأكيد المراجعة</IconText>
                        </button>
                      )}
                      <div className="flex flex-wrap gap-2 ms-auto">
                        {!isRetired && (
                          <button
                            onClick={() => setConfirmRetireId(file.id)}
                            className="btn-danger text-sm py-2 px-4 inline-flex items-center gap-1.5"
                          >
                            <IconText icon={Archive}>تقاعد الملف</IconText>
                          </button>
                        )}
                        <button
                          onClick={() => setConfirmDelete(file.filename)}
                          className="btn-danger text-sm py-2 px-4 inline-flex items-center gap-1.5"
                        >
                          <IconText icon={Trash2}>حذف نهائي</IconText>
                        </button>
                      </div>
                    </div>

                    {/* Confirm retire */}
                    {isConfirmingRetire && (
                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                        <p className="text-sm text-amber-900 mb-2 font-medium">تقاعد الملف</p>
                        <p className="text-xs text-amber-800 mb-3">
                          سيُزال الملف فوراً من قاعدة معرفة الشات بوت ولن يظهر في إجاباته. يبقى الملف محفوظاً
                          في قاعدة البيانات للسجل. يمكنك حذفه نهائياً بعد ذلك إذا أردت.
                        </p>
                        <div className="flex gap-2">
                          <button onClick={() => handleRetireConfirm(file.id)} disabled={retiring}
                            className="btn-danger text-sm py-1.5 px-3">
                            {retiring ? '...' : 'نعم، قاعد الملف'}
                          </button>
                          <button onClick={() => setConfirmRetireId(null)} className="btn-secondary text-sm py-1.5 px-3">إلغاء</button>
                        </div>
                      </div>
                    )}

                    {/* Validity / freshness edit panel */}
                    {isEditingFreshness && (
                      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-3">
                        <p className="text-sm font-semibold text-blue-900 inline-flex items-center gap-1.5">
                          <ClipboardList className="w-4 h-4 shrink-0" aria-hidden="true" />
                          معلومات الملف والصلاحية
                        </p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <label className="label text-xs">صالح حتى</label>
                            <input type="date" className="input text-sm"
                              value={freshnessForm.valid_until}
                              onChange={(e) => setFreshnessForm(f => ({ ...f, valid_until: e.target.value }))} />
                          </div>
                          <div>
                            <label className="label text-xs">موعد المراجعة التالية</label>
                            <input type="date" className="input text-sm"
                              value={freshnessForm.next_review_at}
                              onChange={(e) => setFreshnessForm(f => ({ ...f, next_review_at: e.target.value }))} />
                          </div>
                          <div>
                            <label className="label text-xs">المسؤول (اختياري)</label>
                            <input type="text" className="input text-sm" placeholder="اسم القسم أو الشخص"
                              value={freshnessForm.owner}
                              onChange={(e) => setFreshnessForm(f => ({ ...f, owner: e.target.value }))} />
                          </div>
                          <div>
                            <label className="label text-xs">التصنيف (اختياري)</label>
                            <input type="text" className="input text-sm" placeholder="مثال: أكاديمي، قبول، مالي"
                              value={freshnessForm.category}
                              onChange={(e) => setFreshnessForm(f => ({ ...f, category: e.target.value }))} />
                          </div>
                        </div>
                        <div>
                          <label className="label text-xs">الرابط الرسمي للمستند على موقع الجامعة (اختياري)</label>
                          <input
                            type="url"
                            inputMode="url"
                            autoComplete="off"
                            className="input text-sm w-full"
                            dir="ltr"
                            placeholder="https://www.hebron.edu/..."
                            value={freshnessForm.source_url}
                            onChange={(e) => setFreshnessForm((f) => ({ ...f, source_url: e.target.value }))}
                          />
                          <p className="text-xs text-blue-800/80 mt-1">يُستخدم للمرجعية؛ لا يؤثر على الفهرسة تلقائياً حالياً.</p>
                        </div>
                        {freshnessMsg && (
                          <p className={`text-xs ${freshnessMsg.type === 'success' ? 'text-green-700' : 'text-red-700'}`}>
                            {freshnessMsg.text}
                          </p>
                        )}
                        <div className="flex gap-2 flex-wrap">
                          <button onClick={() => handleSaveFreshness(file.id)} disabled={savingFreshness}
                            className="btn-primary text-sm py-1.5 px-3 inline-flex items-center gap-1.5">
                            {savingFreshness ? 'جاري الحفظ...' : <IconText icon={Save}>حفظ</IconText>}
                          </button>
                          <button onClick={() => setEditFreshnessId(null)} className="btn-secondary text-sm py-1.5 px-3">
                            إغلاق
                          </button>
                        </div>
                      </div>
                    )}

                    {isFailed && (
                      <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 space-y-2">
                        <p className="text-xs font-semibold text-red-800 inline-flex items-center gap-1.5">
                          {file.status === 'indexing' ? (
                            <>
                              <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin" aria-hidden="true" />
                              الفهرسة لم تكتمل بعد
                            </>
                          ) : (
                            <>
                              <XCircle className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                              فشلت عملية الفهرسة
                            </>
                          )}
                        </p>
                        <p className="text-xs text-red-700">
                          الملف محفوظ على القرص لكنه غير متاح في قاعدة معرفة الشات بوت.
                          اضغط "إعادة الفهرسة" للمحاولة مرة أخرى، أو احذف الملف نهائياً إذا كان تالفاً.
                        </p>
                        <button
                          onClick={() => handleReindex(file.id)}
                          disabled={reindexingId === file.id}
                          className="btn-primary text-sm py-1.5 px-4 inline-flex items-center gap-1.5"
                        >
                          {reindexingId === file.id ? (
                            <IconText icon={Loader2} iconClassName="w-4 h-4 shrink-0 animate-spin">جاري الفهرسة...</IconText>
                          ) : (
                            <IconText icon={RefreshCw}>إعادة الفهرسة</IconText>
                          )}
                        </button>
                      </div>
                    )}

                    {isRetired && (
                      <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 space-y-2">
                        <p className="text-xs text-amber-800">
                          هذا الملف متقاعد — تمت إزالته من قاعدة معرفة الشات بوت. يمكنك استعادته أو حذفه نهائياً.
                        </p>
                        <button
                          onClick={() => handleRestore(file.id)}
                          disabled={restoringId === file.id}
                          className="btn-primary text-sm py-1.5 px-4 inline-flex items-center gap-1.5"
                        >
                          {restoringId === file.id ? (
                            <IconText icon={Loader2} iconClassName="w-4 h-4 shrink-0 animate-spin">جاري الاستعادة...</IconText>
                          ) : (
                            <IconText icon={Recycle}>استعادة الملف إلى قاعدة المعرفة</IconText>
                          )}
                        </button>
                      </div>
                    )}

                    {/* Confirm delete prompt */}
                    {isDeleting && (
                      <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                        <p className="text-sm text-red-800 mb-3">هل أنت متأكد من حذف هذا الملف؟ سيتم حذفه من الخادم وChroma.</p>
                        <div className="flex gap-2 flex-wrap">
                          <button
                            onClick={handleDeleteConfirm}
                            className="btn-danger text-sm py-2 px-3"
                          >
                            نعم، احذف
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="btn-secondary text-sm py-2 px-3"
                          >
                            إلغاء
                          </button>
                        </div>
                      </div>
                    )}

                    {/* View chunks section */}
                    {viewChunksFor === file.filename && (
                      <div className="bg-white border border-gray-200 rounded-lg p-3">
                        {chunksLoading ? (
                          <p className="text-gray-500 text-sm">جاري جلب المقاطع...</p>
                        ) : chunks.length === 0 ? (
                          <p className="text-gray-400 text-sm">لا توجد مقاطع لهذا الملف.</p>
                        ) : (
                          <div className="space-y-2 max-h-80 overflow-y-auto">
                            <p className="text-sm font-medium text-gray-700">مقاطع Chroma ({chunks.length})</p>
                            {chunks.map((ch, i) => (
                              <div key={i} className="bg-gray-50 rounded-lg p-2 text-xs text-gray-700 border border-gray-200">
                                <p className="whitespace-pre-wrap leading-relaxed">{ch.page_content}</p>
                                <p className="text-gray-400 mt-1 text-xs">
                                  {Object.entries(ch.metadata).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                                </p>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
