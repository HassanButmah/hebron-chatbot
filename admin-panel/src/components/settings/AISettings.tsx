import { useState, useEffect } from 'react'
import { AlertTriangle, RefreshCw, Save } from 'lucide-react'
import { getSettings, updateSettings, restoreDefaults, AISettings as AISettingsType } from '../../api/settings'
import { IconHeading, IconText } from '../ui/IconText'

interface SectionProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function Section({ title, children, defaultOpen = false }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-4 text-right bg-gray-50 hover:bg-gray-100"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-semibold text-gray-800">{title}</span>
        <span className="text-gray-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="p-4 space-y-4">{children}</div>}
    </div>
  )
}

export default function AISettings() {
  const [settings, setSettings] = useState<AISettingsType | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await getSettings()
      setSettings(data)
    } catch {
      setMsg({ type: 'error', text: 'تعذر جلب الإعدادات' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const set = (key: keyof AISettingsType, value: string) =>
    setSettings((prev) => prev ? { ...prev, [key]: value } : prev)

  const handleSave = async () => {
    if (!settings) return
    setSaving(true); setMsg(null)
    try {
      await updateSettings(settings)
      setMsg({ type: 'success', text: 'تم حفظ الإعدادات بنجاح.' })
    } catch {
      setMsg({ type: 'error', text: 'تعذر حفظ الإعدادات.' })
    } finally {
      setSaving(false)
    }
  }

  const handleRestore = async () => {
    if (!confirm('هل تريد استعادة الإعدادات الافتراضية؟ سيتم مسح التعديلات الحالية.')) return
    setRestoring(true); setMsg(null)
    try {
      await restoreDefaults()
      await load()
      setMsg({ type: 'success', text: 'تمت استعادة الإعدادات الافتراضية.' })
    } catch {
      setMsg({ type: 'error', text: 'تعذر استعادة الإعدادات.' })
    } finally {
      setRestoring(false)
    }
  }

  if (loading) return <p className="text-gray-500 text-center py-8">جاري تحميل الإعدادات...</p>

  return (
    <div className="space-y-5">
      {/* Info */}
      <div className="card bg-amber-50 border-amber-200">
        <IconHeading as="h3" icon={AlertTriangle} className="font-semibold text-amber-900 mb-2">
          دليل هندسة الأوامر
        </IconHeading>
        <ul className="text-sm text-amber-800 space-y-1 list-disc list-inside">
          <li>لا تحذف قواعد منع التخيل — يجب دائماً وجود قاعدة تمنع البوت من تأليف معلومات.</li>
          <li>استخدم صيغة الأمر: البوت يستجيب أفضل للأوامر المباشرة ("استخدم النقاط المرتبة").</li>
          <li>رسائل الاعتذار تُضاف تلقائياً — لا داعي لكتابتها في النص الأساسي.</li>
        </ul>
      </div>

      {settings && (
        <>
          <Section title="النص البرمجي الأساسي">
            <div>
              <label className="label">النص البرمجي بالعربية</label>
              <textarea
                className="input min-h-[200px] resize-y text-sm leading-relaxed"
                value={settings.ar_system_prompt}
                onChange={(e) => set('ar_system_prompt', e.target.value)}
              />
            </div>
            <div>
              <label className="label">النص البرمجي بالإنجليزية</label>
              <textarea
                className="input min-h-[200px] resize-y text-sm leading-relaxed"
                value={settings.en_system_prompt}
                onChange={(e) => set('en_system_prompt', e.target.value)}
              />
            </div>
          </Section>

          <Section title="رسائل الاعتذار">
            <div>
              <label className="label">رسالة عدم المعرفة بالعربية</label>
              <textarea
                className="input min-h-[100px] resize-y text-sm"
                value={settings.ar_dont_know}
                onChange={(e) => set('ar_dont_know', e.target.value)}
              />
            </div>
            <div>
              <label className="label">رسالة عدم المعرفة بالإنجليزية</label>
              <textarea
                className="input min-h-[100px] resize-y text-sm"
                value={settings.en_dont_know}
                onChange={(e) => set('en_dont_know', e.target.value)}
              />
            </div>
          </Section>

          <Section title="رسائل ضعف التطابق">
            <div>
              <label className="label">رسالة ضعف التطابق بالعربية</label>
              <textarea
                className="input min-h-[100px] resize-y text-sm"
                value={settings.ar_low_conf}
                onChange={(e) => set('ar_low_conf', e.target.value)}
              />
            </div>
            <div>
              <label className="label">رسالة ضعف التطابق بالإنجليزية</label>
              <textarea
                className="input min-h-[100px] resize-y text-sm"
                value={settings.en_low_conf}
                onChange={(e) => set('en_low_conf', e.target.value)}
              />
            </div>
          </Section>

          <Section title="رسالة اللغة غير المدعومة">
            <p className="text-xs text-gray-500">
              تُعرض عندما يكتب المستخدم بلغة غير العربية والإنجليزية. الرسالة ثنائية اللغة في حقل واحد.
            </p>
            <div>
              <label className="label">الرسالة</label>
              <textarea
                className="input min-h-[100px] resize-y text-sm"
                value={settings.lang_not_supported}
                onChange={(e) => set('lang_not_supported', e.target.value)}
              />
            </div>
          </Section>

          <Section title="رسائل خارج النطاق">
            <p className="text-xs text-gray-500">
              تُعرض عندما يسأل المستخدم عن موضوع خارج نطاق جامعة الخليل (جامعة أخرى، معلومات عامة…).
            </p>
            <div>
              <label className="label">رسالة خارج النطاق بالعربية</label>
              <textarea
                className="input min-h-[100px] resize-y text-sm"
                value={settings.ar_out_of_scope}
                onChange={(e) => set('ar_out_of_scope', e.target.value)}
              />
            </div>
            <div>
              <label className="label">رسالة خارج النطاق بالإنجليزية</label>
              <textarea
                className="input min-h-[100px] resize-y text-sm"
                value={settings.en_out_of_scope}
                onChange={(e) => set('en_out_of_scope', e.target.value)}
              />
            </div>
          </Section>
        </>
      )}

      {msg && (
        <div className={`px-4 py-3 rounded-lg text-sm ${msg.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' : 'bg-red-50 text-red-800 border border-red-200'
          }`}>
          {msg.text}
        </div>
      )}

      <div className="flex gap-3 flex-wrap">
        <button onClick={handleSave} disabled={saving} className="btn-primary inline-flex items-center gap-2">
          {saving ? 'جاري الحفظ...' : <IconText icon={Save}>حفظ الإعدادات</IconText>}
        </button>
        <button onClick={handleRestore} disabled={restoring} className="btn-secondary inline-flex items-center gap-2">
          {restoring ? 'جاري الاستعادة...' : <IconText icon={RefreshCw}>استعادة الافتراضي</IconText>}
        </button>
      </div>
    </div>
  )
}
