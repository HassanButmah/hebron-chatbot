import { useState, useEffect, useCallback } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  Plug,
  RefreshCw,
  Save,
  Settings,
  X,
  XCircle,
} from 'lucide-react'
import { IconHeading, IconText } from '../ui/IconText'
import { getLLMConfig, saveLLMConfig, testLLMConfig, LLMConfig } from '../../api/llmConfig'

const DEEPSEEK_DEFAULT = {
  api_base_url: 'https://api.deepseek.com',
  model_name: 'deepseek-chat',
}

const OLLAMA_DEFAULT_MODEL = 'deepseek-v3.1:671b-cloud'

export default function LLMSettings() {
  const [config, setConfig] = useState<LLMConfig | null>(null)
  const [loading, setLoading] = useState(true)

  // Form state
  const [provider, setProvider] = useState<'ollama' | 'openai_compatible'>('openai_compatible')
  const [apiBaseUrl, setApiBaseUrl] = useState(DEEPSEEK_DEFAULT.api_base_url)
  const [apiKey, setApiKey] = useState('')
  const [modelName, setModelName] = useState(DEEPSEEK_DEFAULT.model_name)

  // UI state
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; preview?: string; error?: string; latency_ms: number } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const cfg = await getLLMConfig()
      setConfig(cfg)
      setProvider(cfg.provider)
      setApiBaseUrl(cfg.api_base_url || DEEPSEEK_DEFAULT.api_base_url)
      setModelName(cfg.model_name || (cfg.provider === 'ollama' ? OLLAMA_DEFAULT_MODEL : DEEPSEEK_DEFAULT.model_name))
      setApiKey('')  // never pre-fill key
    } catch {
      setMsg({ type: 'error', text: 'تعذر تحميل الإعدادات من الخادم.' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleProviderChange = (p: 'ollama' | 'openai_compatible') => {
    setProvider(p)
    setTestResult(null)
    if (p === 'openai_compatible') {
      setApiBaseUrl(DEEPSEEK_DEFAULT.api_base_url)
      setModelName(DEEPSEEK_DEFAULT.model_name)
    } else {
      setApiBaseUrl('')
      setModelName(OLLAMA_DEFAULT_MODEL)
    }
  }

  const handleReset = () => {
    setProvider('openai_compatible')
    setApiBaseUrl(DEEPSEEK_DEFAULT.api_base_url)
    setModelName(DEEPSEEK_DEFAULT.model_name)
    setApiKey('')
    setMsg({ type: 'success', text: 'تم إعادة تعيين القيم — اضغط حفظ لتطبيق التغييرات.' })
    setTestResult(null)
  }

  const handleSave = async () => {
    setSaving(true)
    setMsg(null)
    setTestResult(null)
    try {
      await saveLLMConfig({ provider, api_base_url: apiBaseUrl, api_key: apiKey, model_name: modelName })
      setMsg({ type: 'success', text: 'تم حفظ الإعدادات وتطبيقها فوراً دون إعادة تشغيل الخادم.' })
      setApiKey('')
      await load()
    } catch (e: unknown) {
      const err = (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'فشل الحفظ'
      setMsg({ type: 'error', text: err })
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await testLLMConfig()
      setTestResult({ ok: res.ok, preview: res.response_preview, error: res.error, latency_ms: res.latency_ms })
    } catch {
      setTestResult({ ok: false, error: 'تعذر الاتصال بخادم API.', latency_ms: 0 })
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return <div className="card text-center text-gray-500 py-12">جاري تحميل الإعدادات...</div>
  }

  const isOpenAI = provider === 'openai_compatible'

  return (
    <div className="space-y-6">

      {/* ── Status card ── */}
      {config && (
        <div className={`card border-2 ${config.provider === 'openai_compatible' ? 'border-indigo-300 bg-indigo-50' : 'border-gray-300 bg-gray-50'}`}>
          <p className="text-sm font-semibold text-gray-700 mb-1">الحالة الحالية (المطبّقة الآن)</p>
          <div className="flex flex-wrap gap-4 text-sm">
            <span>
              <span className="font-medium text-gray-600">المزوّد: </span>
              <code className={`px-2 py-0.5 rounded text-xs font-mono ${config.provider === 'openai_compatible' ? 'bg-indigo-200 text-indigo-900' : 'bg-gray-200 text-gray-800'}`}>
                {config.provider === 'openai_compatible' ? 'OpenAI-compatible (DeepSeek)' : 'Ollama (محلي)'}
              </code>
            </span>
            <span>
              <span className="font-medium text-gray-600">النموذج: </span>
              <code className="bg-white px-2 py-0.5 rounded text-xs border">{config.model_name || '—'}</code>
            </span>
            <span>
              <span className="font-medium text-gray-600">توجيه الأدوات: </span>
              {config.provider === 'openai_compatible'
                ? <span className="text-green-700 font-semibold">✅ مفعّل</span>
                : <span className="text-amber-700">⚠️ معطّل (Ollama لا يدعمه)</span>}
            </span>
            {config.provider === 'openai_compatible' && (
              <span>
                <span className="font-medium text-gray-600">مفتاح API: </span>
                {config.api_key_set
                  ? <span className="text-green-700">● مضبوط</span>
                  : <span className="text-red-600">✗ غير مضبوط</span>}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Form ── */}
      <div className="card space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-800">⚙️ إعداد النموذج اللغوي</h2>
          <button onClick={handleReset} className="btn-secondary text-xs py-1.5 px-3">
            🔄 الافتراضي (DeepSeek)
          </button>
        </div>

        {/* Provider selector */}
        <div>
          <label className="label">مزوّد النموذج</label>
          <div className="flex gap-3 mt-2">
            <label className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 cursor-pointer transition-colors ${
              !isOpenAI ? 'border-primary bg-green-50' : 'border-gray-200 bg-white hover:border-gray-300'
            }`}>
              <input
                type="radio"
                name="provider"
                checked={!isOpenAI}
                onChange={() => handleProviderChange('ollama')}
                className="w-4 h-4 text-primary"
              />
              <div>
                <p className="font-medium text-sm">Ollama (محلي)</p>
                <p className="text-xs text-gray-500">يعمل بدون إنترنت — بدون توجيه أدوات</p>
              </div>
            </label>
            <label className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 cursor-pointer transition-colors ${
              isOpenAI ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:border-gray-300'
            }`}>
              <input
                type="radio"
                name="provider"
                checked={isOpenAI}
                onChange={() => handleProviderChange('openai_compatible')}
                className="w-4 h-4 text-indigo-600"
              />
              <div>
                <p className="font-medium text-sm">API خارجي (DeepSeek / OpenAI)</p>
                <p className="text-xs text-gray-500">يتيح توجيه الأدوات — يحتاج مفتاح API</p>
              </div>
            </label>
          </div>
        </div>

        {/* Model name (always shown) */}
        <div>
          <label className="label">اسم النموذج</label>
          <input
            className="input font-mono"
            placeholder={isOpenAI ? 'deepseek-chat' : 'deepseek-v3.1:671b-cloud'}
            value={modelName}
            onChange={e => setModelName(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-1">
            {isOpenAI ? 'مثال: deepseek-chat أو gpt-4o' : 'اسم النموذج كما يظهر في Ollama'}
          </p>
        </div>

        {/* OpenAI-compatible fields */}
        {isOpenAI && (
          <>
            <div>
              <label className="label">عنوان API الأساسي</label>
              <input
                className="input font-mono"
                placeholder="https://api.deepseek.com"
                value={apiBaseUrl}
                onChange={e => setApiBaseUrl(e.target.value)}
              />
              <p className="text-xs text-gray-400 mt-1">بدون / في النهاية — مثال: https://api.deepseek.com</p>
            </div>
            <div>
              <label className="label">
                مفتاح API
                {config?.api_key_set && (
                  <span className="mr-2 text-xs font-normal text-green-600">● مفتاح محفوظ — اتركه فارغاً للإبقاء عليه</span>
                )}
              </label>
              <input
                type="password"
                className="input font-mono"
                placeholder={config?.api_key_set ? '••••••••••••••••' : 'sk-...'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                autoComplete="new-password"
              />
              <p className="text-xs text-gray-400 mt-1">المفتاح لا يُعرض أبداً بعد الحفظ لأسباب أمنية.</p>
            </div>
          </>
        )}

        {/* Message */}
        {msg && (
          <div className={`px-4 py-3 rounded-lg text-sm border ${
            msg.type === 'success' ? 'bg-green-50 text-green-800 border-green-200' : 'bg-red-50 text-red-800 border-red-200'
          }`}>{msg.text}</div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-3">
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? 'جاري الحفظ...' : '💾 حفظ الإعدادات'}
          </button>
          <button onClick={handleTest} disabled={testing} className="btn-secondary">
            {testing ? '⏳ جاري الاختبار...' : '🔌 اختبار الاتصال'}
          </button>
        </div>
      </div>

      {/* ── Test result ── */}
      {testResult && (
        <div className={`card border-2 ${testResult.ok ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50'}`}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-lg">{testResult.ok ? '✅' : '❌'}</span>
            <span className="font-semibold text-sm text-gray-800">
              {testResult.ok ? 'الاتصال ناجح' : 'فشل الاتصال'}
            </span>
            <span className="text-xs text-gray-500 mr-auto">{testResult.latency_ms} ms</span>
          </div>
          {testResult.ok && testResult.preview && (
            <p className="text-sm text-gray-700 bg-white rounded-lg p-3 border border-green-200 font-arabic">
              {testResult.preview}
            </p>
          )}
          {!testResult.ok && testResult.error && (
            <p className="text-sm text-red-700 font-mono">{testResult.error}</p>
          )}
        </div>
      )}

      {/* ── Info box ── */}
      <div className="card bg-amber-50 border-amber-200">
        <h3 className="font-semibold text-amber-900 mb-2">ℹ️ ملاحظات مهمة</h3>
        <ul className="text-sm text-amber-800 space-y-1 list-disc list-inside">
          <li>التضمين (Embeddings) يعمل دائماً عبر Ollama (bge-m3) بغض النظر عن الإعداد هنا.</li>
          <li>توجيه الأدوات (Tool Routing) يتطلب المزوّد الخارجي — Ollama لا يدعمه.</li>
          <li>التغييرات تُطبَّق فوراً دون إعادة تشغيل الخادم.</li>
          <li>مفتاح API يُخزَّن في قاعدة البيانات — يُوصى بتشفيره في بيئة الإنتاج.</li>
        </ul>
      </div>
    </div>
  )
}
