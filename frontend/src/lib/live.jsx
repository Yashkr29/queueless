import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { API_URL, getToken } from './api'

const Ctx = createContext({ connected: false, subscribe: () => () => {} })

/**
 * ONE authenticated WebSocket per tab with auto-reconnect. The JWT is sent as the first message (never in the URL).
 * Components subscribe with useLiveEvent(handler).
 */
export function LiveProvider({ children }) {
  const subs = useRef(new Set())
  const [connected, setConnected] = useState(false)
  const subscribe = useRef((fn) => { subs.current.add(fn); return () => subs.current.delete(fn) }).current

  useEffect(() => {
    let ws, timer, ping, tries = 0, closed = false
    const url = API_URL.replace(/^http/, 'ws') + '/ws'
    const open = () => {
      ws = new WebSocket(url)
      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: getToken() }))
      ws.onmessage = (e) => {
        if (e.data === 'pong') return
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'ready') { setConnected(true); tries = 0 }
          else subs.current.forEach((fn) => fn(msg))
        } catch { /* ignore malformed frames */ }
      }
      ws.onclose = () => {
        setConnected(false); clearInterval(ping)
        if (!closed) timer = setTimeout(open, Math.min(15000, 1000 * 2 ** tries++))
      }
      ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000)
    }
    open()
    return () => { closed = true; clearTimeout(timer); clearInterval(ping); ws?.close() }
  }, [])

  return <Ctx.Provider value={{ connected, subscribe }}>{children}</Ctx.Provider>
}

export const useLiveStatus = () => useContext(Ctx).connected

export function useLiveEvent(handler) {
  const { subscribe } = useContext(Ctx)
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => subscribe((m) => ref.current(m)), [subscribe])
}

/** Fetch + optional auto-refresh. */
export function usePoll(fn, deps = [], ms = 0) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const fnRef = useRef(fn)
  fnRef.current = fn
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let live = true
    fnRef.current()
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error) => live && setState((s) => ({ ...s, error, loading: false })))
    return () => { live = false }
  }, [...deps, tick]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!ms) return
    const t = setInterval(() => setTick((x) => x + 1), ms)
    return () => clearInterval(t)
  }, [ms])
  return { ...state, reload: () => setTick((x) => x + 1) }
}

/** Coalesces bursts of live events into one refetch (a single action can fan out several WebSocket messages). */
export function useDebounced(fn, ms = 1200) {
  const ref = useRef(fn)
  ref.current = fn
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])
  return useRef(() => { clearTimeout(timer.current); timer.current = setTimeout(() => ref.current(), ms) }).current
}
