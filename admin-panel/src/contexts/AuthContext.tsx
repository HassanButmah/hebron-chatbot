import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { login as apiLogin, AdminUser } from '../api/auth'

interface AuthContextValue {
  user: AdminUser | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AdminUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('admin_token')
    const stored = localStorage.getItem('admin_user')
    if (token && stored) {
      try {
        setUser(JSON.parse(stored))
      } catch {
        localStorage.removeItem('admin_token')
        localStorage.removeItem('admin_user')
      }
    }
    setLoading(false)
  }, [])

  const login = async (username: string, password: string) => {
    const data = await apiLogin(username, password)
    localStorage.setItem('admin_token', data.token)
    const u: AdminUser = { username: data.username, role: data.role }
    localStorage.setItem('admin_user', JSON.stringify(u))
    setUser(u)
  }

  const logout = () => {
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
