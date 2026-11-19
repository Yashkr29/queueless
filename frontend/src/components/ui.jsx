import { createContext, useCallback, useContext, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { STATUS } from '../lib/format'

const cx = (...a) => a.filter(Boolean).join(' ')

export function Card({ className, children, ...p }) {
  return <section className={cx('rounded-[28px] border border-line bg-white p-6', className)} {...p}>{children}</section>
}
export function CardTitle({ children, right, sub }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div><h3 className="font-display text-[19px] font-semibold tracking-tight text-ink">{children}</h3>{sub && <p className="mt-1 text-[13px] text-muted">{sub}</p>}</div>
      {right}
    </div>
  )
}

const TONES = {
  slate: 'bg-slate-100 text-slate-600', blue: 'bg-brand-100 text-brand-600', amber: 'bg-[#fbecc8] text-[#7a4205]',
  violet: 'bg-brand-100 text-brand-600', green: 'bg-[#dcefe4] text-[#0b5a3c]', red: 'bg-[#f9dcd8] text-[#8f1a10]',
}
export function Badge({ tone = 'slate', children, className, ...p }) {
  return <span className={cx('inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold', TONES[tone], className)} {...p}>{children}</span>
}
export function StatusBadge({ status }) {
  const s = STATUS[status] || { label: status, tone: 'slate' }
  if (status === 'serving') return <span className="inline-flex items-center rounded-full bg-brand-600 px-2.5 py-1 text-xs font-semibold text-brand-50">{s.label}</span>
  return <Badge tone={s.tone}>{s.label}</Badge>
}

const BTN = {
  primary: 'bg-brand-600 text-brand-50 hover:bg-brand-700',
  soft: 'bg-brand-100 text-brand-600 hover:bg-brand-200/60',
  ghost: 'bg-white text-brand-600 ring-1 ring-brand-200 hover:bg-brand-50',
  danger: 'bg-[#fdf1ef] text-[#8f1a10] ring-1 ring-[#e6c3bd] hover:bg-[#fae4e0]',
}
export function Button({ variant = 'primary', size = 'md', className, loading, children, ...p }) {
  return (
    <button className={cx('inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-colors', size === 'sm' ? 'min-h-10 px-4 text-[13px]' : 'min-h-11 px-6 text-sm', BTN[variant], className)}
      disabled={loading || p.disabled} {...p}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}{children}
    </button>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}
export const inputCls = 'w-full min-h-11 rounded-2xl border border-brand-200 bg-white px-4 py-2.5 text-sm text-ink placeholder:text-muted/70 focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-200/40'
export const Input = (p) => <input className={inputCls} {...p} />
export const Select = ({ children, className, ...p }) => <select className={cx(inputCls, 'pr-8', className)} {...p}>{children}</select>

export function Sparkline({ values = [], className = 'h-8 w-full' }) {
  if (values.length < 2) return <div className={className} />
  const w = 120, h = 32, pad = 3
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - pad - ((v - lo) / span) * (h - pad * 2)}`)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={className} aria-hidden>
      <path d={`M${pts.join(' L')}`} fill="none" stroke="#124559" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function Stat({ icon: Icon, label, value, unit, hint, delta, deltaTone = 'slate', spark }) {
  return (
    <Card className="!p-5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-[13px] font-medium text-muted">{Icon && <Icon className="h-4 w-4" aria-hidden />}{label}</span>
        {delta && <Badge tone={deltaTone}>{delta}</Badge>}
      </div>
      <p className="mt-3 flex items-baseline gap-1.5"><span className="font-display text-4xl font-semibold leading-none tracking-tight">{value ?? '—'}</span>{unit && <span className="text-[13px] text-muted">{unit}</span>}</p>
      {spark ? <div className="mt-3"><Sparkline values={spark} /></div> : null}
      {hint && <p className="mt-2 text-xs text-muted">{hint}</p>}
    </Card>
  )
}

export function Spinner({ label = 'Loading…' }) {
  return <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted" role="status"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{label}</div>
}
export function Empty({ icon: Icon = Info, title, children }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-100 text-brand-500"><Icon className="h-6 w-6" aria-hidden /></span>
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="max-w-sm text-sm text-muted">{children}</p>}
    </div>
  )
}
export function ErrorBox({ children }) {
  return <div role="alert" className="flex items-start gap-2 rounded-2xl bg-[#f9dcd8] px-4 py-3 text-sm text-[#8f1a10]"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{children}</div>
}
export function PageHeader({ title, sub, eyebrow, actions, badge }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <p className="mb-1.5 text-[13px] font-medium text-muted">{eyebrow}</p>}
        <div className="flex flex-wrap items-center gap-3"><h1 className="font-display text-[34px] font-semibold leading-[1.1] tracking-tight md:text-4xl">{title}</h1>{badge}</div>
        {sub && <p className="mt-2 text-sm text-muted">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Modal({ open, onClose, title, children }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-[32px] bg-white px-6 pb-7 pt-3 shadow-2xl sm:rounded-[28px] sm:pt-6" onClick={(e) => e.stopPropagation()}>
        <span className="mx-auto mb-3 block h-1.5 w-11 rounded-full bg-brand-200/70 sm:hidden" aria-hidden />
        <div className="mb-4 flex items-start justify-between gap-3"><h2 className="font-display text-2xl font-semibold tracking-tight">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-full p-2 text-muted hover:bg-brand-50"><X className="h-5 w-5" /></button></div>
        {children}
      </div>
    </div>
  )
}

/** Semi-circular gauge (value 0..1). */
export function Gauge({ value = 0, label, sub }) {
  const v = Math.max(0, Math.min(1, value))
  const r = 64, c = Math.PI * r
  return (
    <div className="relative mx-auto w-[160px]">
      <svg viewBox="0 0 160 92" className="w-full" role="img" aria-label={`${label}: ${Math.round(v * 100)}%`}>
        <path d="M16 84A64 64 0 0 1 144 84" fill="none" stroke="#e3ecdc" strokeWidth="14" strokeLinecap="round" />
        <path d="M16 84A64 64 0 0 1 144 84" fill="none" stroke="#124559" strokeWidth="14" strokeLinecap="round" strokeDasharray={`${c * v} ${c}`} />
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center"><p className="font-display text-[28px] font-semibold leading-none">{Math.round(v * 100)}%</p>{sub && <p className="mt-1 text-xs text-muted">{sub}</p>}</div>
    </div>
  )
}

/** Range bar with a point estimate (customer wait estimate). */
export function RangeBar({ value, lower, upper, max = 60 }) {
  const m = Math.max(max, Math.ceil((upper ?? value) * 1.25))
  const pct = (x) => `${Math.min(100, Math.max(0, (x / m) * 100))}%`
  return (
    <div>
      <div className="relative h-3.5 rounded-full bg-slate-100" role="img" aria-label={lower != null ? `Expected range ${Math.round(lower)} to ${Math.round(upper)} minutes` : `About ${Math.round(value)} minutes`}>
        {lower != null && <span className="absolute inset-y-0 rounded-full bg-brand-200" style={{ left: pct(lower), width: `calc(${pct(upper)} - ${pct(lower)})` }} />}
        <span className="absolute -top-1 h-[22px] w-[22px] -translate-x-1/2 rounded-full border-4 border-white bg-brand-600 shadow-md" style={{ left: pct(value) }} />
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted"><span>0 min</span>{lower != null && <span className="font-semibold text-brand-600">Expected range {Math.round(lower)}–{Math.round(upper)} min</span>}<span>{m}</span></div>
    </div>
  )
}

export function DemoBanner({ show }) {
  if (!show) return null
  return (
    <div className="mb-5 flex items-center gap-2 rounded-2xl bg-[#fbecc8] px-4 py-2.5 text-sm text-[#7a4205]">
      <Info className="h-4 w-4 shrink-0" aria-hidden />
      <span><b>Demo data.</b> Historical figures here come from a simulator and are flagged <code>is_demo</code>. They are not real customers and not evidence of real-world accuracy.</span>
    </div>
  )
}

export function EstimateBadge({ estimate }) {
  if (!estimate) return null
  const map = { ml: ['blue', 'AI estimate'], fallback: ['slate', 'Standard estimate (non-AI)'], unavailable: ['amber', 'No estimate'] }
  const [tone, label] = map[estimate.method] || map.fallback
  return <Badge tone={tone} title={estimate.note}>{label}</Badge>
}

/* ---- toasts ---- */
const ToastCtx = createContext(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((message, tone = 'info') => {
    const id = Math.random()
    setItems((s) => [...s, { id, message, tone }])
    setTimeout(() => setItems((s) => s.filter((i) => i.id !== id)), 5000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-24 right-4 z-[60] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2 lg:bottom-4" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto flex items-start gap-2 rounded-2xl bg-ink px-4 py-3 text-sm text-white shadow-xl">
            {t.tone === 'error' ? <AlertTriangle className="mt-0.5 h-4 w-4 text-red-300" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 text-brand-200" />}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
