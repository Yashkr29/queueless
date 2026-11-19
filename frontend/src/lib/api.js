// Single API client. Data contracts mirror backend/app/schemas.py.
import axios from 'axios'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const KEY = 'queueless.token'
const LOC_KEY = 'queueless.location'

export const getToken = () => localStorage.getItem(KEY)
export const setToken = (t) => (t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY))
export const getActiveLocation = () => localStorage.getItem(LOC_KEY)
export const setActiveLocation = (id) => (id ? localStorage.setItem(LOC_KEY, String(id)) : localStorage.removeItem(LOC_KEY))

export const api = axios.create({ baseURL: API_URL, timeout: 20000 })

api.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  const loc = getActiveLocation()
  if (loc) cfg.headers['X-Location-Id'] = loc   // which organization this request operates on
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && getToken()) {
      setToken(null)
      window.location.assign('/login')
    }
    return Promise.reject(err)
  },
)

export function errorMessage(err, fallback = 'Something went wrong. Please try again.') {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x) => x.msg?.replace(/^Value error, /, '')).filter(Boolean).join('; ') || fallback
  if (err?.code === 'ERR_NETWORK') return 'Cannot reach the QueueLess server. Check that the backend is running.'
  return fallback
}

export async function download(path, filename) {
  const r = await api.get(path, { responseType: 'blob' })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
