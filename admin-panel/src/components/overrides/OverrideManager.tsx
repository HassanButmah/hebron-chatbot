import { useState, FormEvent } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Clock,
  Lightbulb,
  Plus,
  Save,
  Settings,
  Trash2,
} from 'lucide-react'
import { IconHeading, IconText } from '../ui/IconText'
import { listOverrides, addOverride, updateOverride, deleteOverride, Override } from '../../api/overrides'
import { useData } from '../../hooks/useData'

const TRIGGER_HINT = 'افصل بين العبارات بـ (،) أو (,) أو (/) أو (|). مثال: موعد التخرج / حفل التخرج'

interface EditState { trigger_phrase: string; answer: string }

export default function OverrideManager() {
  const { data: overrides, loading, error, refresh } = useData(listOverrides)

  const [newTrigger, setNewTrigger] = useState('')
  const [newAnswer, setNewAnswer] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)

  const [editState, setEditState] = useState<Record<number, EditState>>({})
  const [expanded, setExpanded] = useState<number | null>(null)
  const [saving, setSaving] = useState<number | null>(null)
  const [saveMsg, setSaveMsg] = useState<Record<number, string>>({})

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    if (!newTrigger.trim() || !newAnswer.trim()) { setAddError('يرجى ملء جميع الحقول'); return }
    setAdding(true); setAddError('')
    try {
      await addOverride(newTrigger.trim(), newAnswer.trim())
      setNewTrigger(''); setNewAnswer(''); setShowAddForm(false)
      refresh()
    } catch {
      setAddError('تعذر الإضافة')
    } finally {
      setAdding(false)
    }
  }

  const getEdit = (ov: Override): EditState =>
    editState[ov.id] ?? { trigger_phrase: ov.trigger_phrase, answer: ov.answer }

  const setEdit = (ov: Override, partial: Partial<EditState>) =>
    setEditState((p) => ({ ...p, [ov.id]: { ...getEdit(ov), ...partial } }))

  const handleSave = async (ov: Override) => {
    const state = getEdit(ov)
    setSaving(ov.id)
    try {
      await updateOverride(ov.id, state.trigger_phrase, state.answer)
      setSaveMsg((p) => ({ ...p, [ov.id]: 'تم الحفظ' }))
      refresh()
    } catch {
      setSaveMsg((p) => ({ ...p, [ov.id]: 'فشل الحفظ' }))
    } finally {
      setSaving(null)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('هل تريد حذف هذه الإجابة المخصصة؟')) return
    try {
      await deleteOverride(id)
      refresh()
    } catch {
      alert('تعذر الحذف')
    }
  }

  return (
    <div className="space-y-6">
      {/* Info box */}
      <div className="card bg-blue-50 border-blue-200">
        <h3 className="font-semibold text-blue-900 mb-2">💡 كيف تعمل الإجابات المخصصة؟</h3>
        <ul className="text-sm text-blue-800 space-y-1 list-disc list-inside">
          <li>يمكن إضافة عدة صيغ للسؤال في نفس الحقل، مفصولة بـ (،) أو (/) أو (|).</li>
          <li>لكي يُفعَّل الرد، يجب أن تشكّل العبارة 70% على الأقل من نص سؤال الطالب.</li>
          <li>إذا كان السؤال مركباً يتضمن موضوعات مختلفة، يُحوَّل للذكاء الاصطناعي بالكامل.</li>
        </ul>
      </div>

      {/* Add button */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-800">⚙️ الإجابات المخصصة</h2>
          <button
            onClick={() => setShowAddForm((v) => !v)}
            className="btn-primary text-sm py-1.5 px-3"
          >
            {showAddForm ? 'إلغاء' : '➕ إضافة جديد'}
          </button>
        </div>

        {showAddForm && (
          <form onSubmit={handleAdd} className="border border-gray-200 rounded-xl p-4 bg-gray-50 space-y-3 mb-4">
            <div>
              <label className="label">عبارة التفعيل (trigger)</label>
              <input
                type="text"
                className="input"
                placeholder={TRIGGER_HINT}
                value={newTrigger}
                onChange={(e) => setNewTrigger(e.target.value)}
                disabled={adding}
              />
              <p className="text-xs text-gray-500 mt-1">{TRIGGER_HINT}</p>
            </div>
            <div>
              <label className="label">الإجابة الإدارية</label>
              <textarea
                className="input min-h-[120px] resize-y"
                value={newAnswer}
                onChange={(e) => setNewAnswer(e.target.value)}
                disabled={adding}
              />
            </div>
            {addError && <p className="text-red-600 text-sm">{addError}</p>}
            <button type="submit" className="btn-primary" disabled={adding}>
              {adding ? 'جاري الإضافة...' : '➕ إضافة'}
            </button>
          </form>
        )}

        {loading && <p className="text-gray-500 text-center py-8">جاري التحميل...</p>}
        {error && <p className="text-red-600 text-center py-4">تعذر جلب البيانات.</p>}
        {!loading && !error && (overrides?.length === 0) && (
          <p className="text-gray-400 text-center py-8">لا توجد إجابات مخصصة بعد.</p>
        )}

        <div className="space-y-2">
          {overrides?.map((ov) => {
            const state = getEdit(ov)
            const isOpen = expanded === ov.id
            const preview = ov.trigger_phrase.length > 80 ? ov.trigger_phrase.slice(0, 80) + '…' : ov.trigger_phrase
            return (
              <div key={ov.id} className="border border-gray-200 rounded-xl overflow-hidden">
                <button
                  className="w-full flex items-center justify-between p-4 text-right hover:bg-gray-50"
                  onClick={() => setExpanded(isOpen ? null : ov.id)}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-xs text-gray-400 flex-shrink-0">#{ov.id}</span>
                    <span className="text-sm text-gray-800 truncate">{preview}</span>
                  </div>
                  <span className="text-gray-400 text-sm flex-shrink-0 mr-2">{isOpen ? '▲' : '▼'}</span>
                </button>

                {isOpen && (
                  <div className="border-t border-gray-100 p-4 bg-gray-50 space-y-3">
                    {ov.created_at && (
                      <p className="text-xs text-gray-400">🕒 {new Date(ov.created_at.includes('Z') || ov.created_at.includes('+') ? ov.created_at : ov.created_at.replace(' ', 'T') + 'Z').toLocaleString('ar-SA', { timeZone: 'Asia/Hebron' })}</p>
                    )}
                    <div>
                      <label className="label text-xs">عبارة التفعيل</label>
                      <input
                        type="text"
                        className="input text-sm"
                        value={state.trigger_phrase}
                        onChange={(e) => setEdit(ov, { trigger_phrase: e.target.value })}
                      />
                      <p className="text-xs text-gray-500 mt-1">{TRIGGER_HINT}</p>
                    </div>
                    <div>
                      <label className="label text-xs">الإجابة</label>
                      <textarea
                        className="input text-sm min-h-[120px] resize-y"
                        value={state.answer}
                        onChange={(e) => setEdit(ov, { answer: e.target.value })}
                      />
                    </div>
                    {saveMsg[ov.id] && <p className="text-xs text-gray-600">{saveMsg[ov.id]}</p>}
                    <div className="flex gap-2">
                      <button onClick={() => handleSave(ov)} disabled={saving === ov.id} className="btn-primary text-sm py-1.5 px-3">
                        {saving === ov.id ? 'جاري الحفظ...' : '💾 حفظ'}
                      </button>
                      <button onClick={() => handleDelete(ov.id)} className="btn-danger text-sm py-1.5 px-3">
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
