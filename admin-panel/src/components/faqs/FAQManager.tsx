import { useState, FormEvent } from 'react'
import {
  ChevronDown,
  ChevronUp,
  ListOrdered,
  Plus,
  Save,
  Search,
  Trash2,
} from 'lucide-react'
import { IconHeading, IconText } from '../ui/IconText'
import { listFAQs, addFAQ, updateFAQ, deleteFAQ, normalizeFAQOrder, FAQ } from '../../api/faqs'
import { useData } from '../../hooks/useData'

type SortOption = 'order' | 'count_desc' | 'count_asc' | 'newest' | 'oldest' | 'q_asc' | 'q_desc'

function sortFAQs(faqs: FAQ[], sort: SortOption): FAQ[] {
  const list = [...faqs]
  const toDate = (d: string | null) => (d ? new Date(d).getTime() : 0)
  switch (sort) {
    case 'order': return list.sort((a, b) => a.display_order - b.display_order || a.id - b.id)
    case 'count_desc': return list.sort((a, b) => b.question_count - a.question_count)
    case 'count_asc': return list.sort((a, b) => a.question_count - b.question_count)
    case 'newest': return list.sort((a, b) => toDate(b.created_at) - toDate(a.created_at))
    case 'oldest': return list.sort((a, b) => toDate(a.created_at) - toDate(b.created_at))
    case 'q_asc': return list.sort((a, b) => a.question.localeCompare(b.question))
    case 'q_desc': return list.sort((a, b) => b.question.localeCompare(a.question))
  }
}

interface EditState {
  question: string
  answer: string
  display_order: number
}

export default function FAQManager() {
  const { data: faqs, loading, error, refresh } = useData(listFAQs)

  const [newQ, setNewQ] = useState('')
  const [newA, setNewA] = useState('')
  const [addingError, setAddingError] = useState('')
  const [adding, setAdding] = useState(false)

  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortOption>('order')

  const [editState, setEditState] = useState<Record<number, EditState>>({})
  const [expanded, setExpanded] = useState<number | null>(null)
  const [saving, setSaving] = useState<number | null>(null)
  const [savingMsg, setSavingMsg] = useState<Record<number, string>>({})
  const [normalizing, setNormalizing] = useState(false)

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    if (!newQ.trim() || !newA.trim()) { setAddingError('يرجى ملء السؤال والإجابة'); return }
    setAdding(true)
    setAddingError('')
    try {
      await addFAQ(newQ.trim(), newA.trim())
      setNewQ(''); setNewA('')
      refresh()
    } catch {
      setAddingError('تعذر إضافة السؤال الشائع')
    } finally {
      setAdding(false)
    }
  }

  const getEdit = (faq: FAQ): EditState =>
    editState[faq.id] ?? { question: faq.question, answer: faq.answer, display_order: faq.display_order }

  const setEdit = (faq: FAQ, partial: Partial<EditState>) =>
    setEditState((prev) => ({ ...prev, [faq.id]: { ...getEdit(faq), ...partial } }))

  const handleSave = async (faq: FAQ) => {
    const state = getEdit(faq)
    setSaving(faq.id)
    try {
      await updateFAQ(faq.id, state.question, state.answer, state.display_order)
      setSavingMsg((p) => ({ ...p, [faq.id]: 'تم الحفظ' }))
      refresh()
    } catch {
      setSavingMsg((p) => ({ ...p, [faq.id]: 'فشل الحفظ' }))
    } finally {
      setSaving(null)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('هل تريد حذف هذا السؤال؟')) return
    try {
      await deleteFAQ(id)
      refresh()
    } catch {
      alert('تعذر حذف السؤال')
    }
  }

  const handleNormalize = async () => {
    setNormalizing(true)
    try {
      await normalizeFAQOrder()
      refresh()
    } catch {
      alert('تعذر إعادة الترتيب')
    } finally {
      setNormalizing(false)
    }
  }

  const q = search.trim().toLowerCase()
  const filtered = sortFAQs(
    (faqs ?? []).filter((f) =>
      !q || f.question.toLowerCase().includes(q) || f.answer.toLowerCase().includes(q)
    ),
    sort
  )

  return (
    <div className="space-y-6">
      {/* Add new FAQ */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">➕ إضافة سؤال شائع جديد</h2>
        <form onSubmit={handleAdd} className="space-y-3">
          <div>
            <label className="label">السؤال</label>
            <input type="text" className="input" value={newQ} onChange={(e) => setNewQ(e.target.value)} placeholder="اكتب السؤال هنا..." disabled={adding} />
          </div>
          <div>
            <label className="label">الإجابة</label>
            <textarea className="input min-h-[100px] resize-y" value={newA} onChange={(e) => setNewA(e.target.value)} placeholder="اكتب الإجابة هنا..." disabled={adding} />
          </div>
          {addingError && <p className="text-red-600 text-sm">{addingError}</p>}
          <button type="submit" className="btn-primary" disabled={adding}>
            {adding ? 'جاري الإضافة...' : '➕ إضافة'}
          </button>
        </form>
      </div>

      {/* FAQ list */}
      <div className="card">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h2 className="text-lg font-semibold text-gray-800">الأسئلة الحالية</h2>
          <button onClick={handleNormalize} disabled={normalizing} className="btn-secondary text-sm py-1.5 px-3">
            🧹 ترتيب تلقائي (1..N)
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          <input type="text" className="input text-sm" placeholder="🔍 بحث في الأسئلة..." value={search} onChange={(e) => setSearch(e.target.value)} />
          <select className="input text-sm" value={sort} onChange={(e) => setSort(e.target.value as SortOption)}>
            <option value="order">حسب الترتيب</option>
            <option value="count_desc">الأكثر سؤالاً</option>
            <option value="count_asc">الأقل سؤالاً</option>
            <option value="newest">الأحدث أولاً</option>
            <option value="oldest">الأقدم أولاً</option>
            <option value="q_asc">حسب السؤال (أ–ي)</option>
            <option value="q_desc">حسب السؤال (ي–أ)</option>
          </select>
        </div>

        {loading && <p className="text-gray-500 text-center py-8">جاري التحميل...</p>}
        {error && <p className="text-red-600 text-center py-4">تعذر جلب الأسئلة.</p>}
        {!loading && filtered.length === 0 && <p className="text-gray-400 text-center py-8">لا توجد أسئلة.</p>}

        <div className="space-y-2">
          {filtered.map((faq) => {
            const state = getEdit(faq)
            const isOpen = expanded === faq.id
            return (
              <div key={faq.id} className="border border-gray-200 rounded-xl overflow-hidden">
                <button
                  className="w-full flex items-center justify-between p-4 text-right hover:bg-gray-50"
                  onClick={() => setExpanded(isOpen ? null : faq.id)}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-xs text-gray-400 flex-shrink-0">#{faq.id}</span>
                    <span className="text-sm font-medium text-gray-800 truncate">{faq.question}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 mr-2">
                    <span className="badge-gray text-xs">{faq.question_count} مرة</span>
                    <span className="text-gray-400 text-sm">{isOpen ? '▲' : '▼'}</span>
                  </div>
                </button>

                {isOpen && (
                  <div className="border-t border-gray-100 p-4 bg-gray-50 space-y-3">
                    <div>
                      <label className="label text-xs">السؤال</label>
                      <input
                        type="text"
                        className="input text-sm"
                        value={state.question}
                        onChange={(e) => setEdit(faq, { question: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="label text-xs">الإجابة</label>
                      <textarea
                        className="input text-sm min-h-[100px] resize-y"
                        value={state.answer}
                        onChange={(e) => setEdit(faq, { answer: e.target.value })}
                      />
                    </div>
                    <div className="w-32">
                      <label className="label text-xs">الترتيب</label>
                      <input
                        type="number"
                        className="input text-sm"
                        min={1}
                        value={state.display_order}
                        onChange={(e) => setEdit(faq, { display_order: Number(e.target.value) })}
                      />
                    </div>
                    {savingMsg[faq.id] && (
                      <p className="text-xs text-gray-600">{savingMsg[faq.id]}</p>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleSave(faq)}
                        disabled={saving === faq.id}
                        className="btn-primary text-sm py-1.5 px-3"
                      >
                        {saving === faq.id ? 'جاري الحفظ...' : '💾 حفظ'}
                      </button>
                      <button
                        onClick={() => handleDelete(faq.id)}
                        className="btn-danger text-sm py-1.5 px-3"
                      >
                        🗑️ حذف
                      </button>
                    </div>
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
