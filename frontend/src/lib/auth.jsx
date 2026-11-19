import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getToken, setActiveLocation, setToken } from './api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!getToken())

  useEffect(() => {
    if (!getToken()) return
    api.get('/auth/me').then((r) => setUser(r.data)).catch(() => setToken(null)).finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email, password) => {
    const r = await api.post('/auth/login', { email, password })
    setToken(r.data.access_token); setUser(r.data.user); return r.data.user
  }, [])
  const register = useCallback(async (payload) => {
    const r = await api.post('/auth/register', payload)
    setToken(r.data.access_token); setUser(r.data.user); return r.data.user
  }, [])
  const logout = useCallback(() => { setToken(null); setActiveLocation(null); setUser(null) }, [])

  const value = useMemo(() => ({ user, setUser, loading, login, register, logout, isStaff: user && user.role !== 'customer' }), [user, loading, login, register, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
