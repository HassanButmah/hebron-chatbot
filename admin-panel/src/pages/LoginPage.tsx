import { useState, FormEvent } from 'react'
import { useAuth } from '../contexts/AuthContext'
import adminLogo from '../assets/admin_logo.png'

export default function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('يرجى إدخال اسم المستخدم وكلمة المرور')
      return
    }
    setLoading(true)
    setError('')
    try {
      await login(username.trim(), password)
    } catch {
      setError('اسم المستخدم أو كلمة المرور غير صحيحة')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="bg-white rounded-2xl shadow-lg w-full max-w-md p-8">
        <div className="text-center mb-8">
          <div className="w-24 h-24 rounded-full overflow-hidden mx-auto mb-4 bg-white flex items-center justify-center">
            <img
              src={adminLogo}
              alt="Hebron University logo"
              className="h-full w-auto max-w-none"
            />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">لوحة إدارة شات بوت جامعة الخليل</h1>
          <p className="text-gray-500 mt-2 text-sm leading-relaxed">
            هذه الواجهة مخصصة للمسؤولين المعتمدين فقط. يرجى إدخال بيانات الدخول للمتابعة.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="label">اسم المستخدم</label>
            <input
              type="text"
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="أدخل اسم المستخدم"
              autoComplete="username"
              disabled={loading}
            />
          </div>
          <div>
            <label className="label">كلمة المرور</label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="أدخل كلمة المرور"
              autoComplete="current-password"
              disabled={loading}
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
              {error}
            </div>
          )}

          <button type="submit" className="btn-primary w-full py-3 text-base" disabled={loading}>
            {loading ? 'جاري التحقق...' : 'تسجيل الدخول'}
          </button>
        </form>
      </div>
    </div>
  )
}
