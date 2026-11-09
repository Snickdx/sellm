import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { AUTH_TOKEN_KEY, fetchMe, type User } from './api/client'

interface AuthState {
  user: User | null
  loading: boolean
  setToken: (token: string | null) => void
  refresh: () => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY)
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const me = await fetchMe()
      setUser(me)
    } catch {
      localStorage.removeItem(AUTH_TOKEN_KEY)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const setToken = useCallback(
    (token: string | null) => {
      if (token) localStorage.setItem(AUTH_TOKEN_KEY, token)
      else localStorage.removeItem(AUTH_TOKEN_KEY)
      void refresh()
    },
    [refresh],
  )

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, setToken, refresh, logout }),
    [user, loading, setToken, refresh, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
