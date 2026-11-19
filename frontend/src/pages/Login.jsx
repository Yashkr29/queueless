import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertTriangle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { errorMessage } from '../lib/api'

/* Palette: #aec3b0 sage · #eff6e0 cream · #598392 teal · #124559 deep teal · #01161e ink */

function Scene() {
  return (
    <svg viewBox="0 0 800 700" preserveAspectRatio="xMinYMax meet" overflow="visible" className="absolute inset-0 h-full w-full" aria-hidden>
      <defs>
        <linearGradient id="wall" gradientUnits="userSpaceOnUse" x1="0" y1="-200" x2="0" y2="470"><stop offset="0" stopColor="#eff6e0" /><stop offset="1" stopColor="#cfdcc6" /></linearGradient>
        <linearGradient id="floor" gradientUnits="userSpaceOnUse" x1="0" y1="470" x2="0" y2="760"><stop offset="0" stopColor="#598392" /><stop offset="1" stopColor="#124559" /></linearGradient>
      </defs>
      <rect x="-2000" y="-2000" width="6000" height="2470" fill="url(#wall)" />
      <polygon points="-2000,470 4000,470 4000,2000 -2000,2000" fill="url(#floor)" />
      <rect x="-2000" y="462" width="6000" height="10" fill="#aec3b0" opacity=".7" />
      <g transform="translate(-50 0)">

      {/* wall clock */}
      <circle cx="330" cy="92" r="30" fill="#eff6e0" stroke="#01161e" strokeWidth="6" />
      <path d="M330 92V72M330 92l14 8" stroke="#01161e" strokeWidth="4" strokeLinecap="round" />

      {/* queue display board */}
      <g transform="translate(60 120)">
        <rect width="210" height="130" rx="16" fill="#124559" />
        <rect x="12" y="12" width="186" height="106" rx="10" fill="#01161e" />
        <text x="105" y="42" textAnchor="middle" fontSize="13" letterSpacing="3" fill="#aec3b0" fontFamily="Inter, sans-serif">NOW SERVING</text>
        <text x="105" y="88" textAnchor="middle" fontSize="40" fontWeight="700" fill="#eff6e0" fontFamily="Inter, sans-serif">A-024</text>
        <circle cx="105" cy="104" r="3" fill="#598392" /><circle cx="117" cy="104" r="3" fill="#aec3b0" /><circle cx="93" cy="104" r="3" fill="#aec3b0" />
      </g>

      {/* plant */}
      <g transform="translate(610 250)">
        <path d="M60 210C20 170 25 90 60 20C95 90 100 170 60 210Z" fill="#598392" />
        <path d="M60 210C95 180 120 130 112 70C80 110 62 150 60 210Z" fill="#124559" opacity=".85" />
        <path d="M60 210C30 185 10 140 18 90C45 120 58 160 60 210Z" fill="#aec3b0" />
        <path d="M32 205h56l-8 62H40Z" fill="#aec3b0" /><rect x="28" y="198" width="64" height="14" rx="6" fill="#598392" />
      </g>

      {/* chair */}
      <g>
        <rect x="395" y="330" width="120" height="170" rx="30" fill="#124559" />
        <rect x="372" y="480" width="150" height="22" rx="11" fill="#01161e" />
        <path d="M447 502v66M447 568l-46 34M447 568l46 34" stroke="#01161e" strokeWidth="9" strokeLinecap="round" />
      </g>

      {/* desk */}
      <g>
        <rect x="150" y="445" width="400" height="22" rx="8" fill="#124559" />
        <rect x="150" y="467" width="400" height="8" fill="#01161e" opacity=".35" />
        <rect x="176" y="475" width="14" height="150" fill="#01161e" /><rect x="510" y="475" width="14" height="150" fill="#01161e" />
        {/* laptop */}
        <path d="M260 445l14-80h140l14 80Z" fill="#aec3b0" />
        <rect x="280" y="378" width="115" height="8" rx="4" fill="#598392" /><rect x="280" y="396" width="80" height="8" rx="4" fill="#598392" opacity=".7" /><rect x="280" y="414" width="100" height="8" rx="4" fill="#598392" opacity=".5" />
        <rect x="244" y="443" width="190" height="8" rx="4" fill="#eff6e0" />
        {/* ticket + mug */}
        <rect x="470" y="425" width="46" height="20" rx="3" fill="#eff6e0" transform="rotate(-6 493 435)" /><rect x="478" y="432" width="26" height="3" fill="#598392" transform="rotate(-6 493 435)" />
        <rect x="190" y="418" width="30" height="27" rx="5" fill="#598392" /><path d="M220 426h8a7 7 0 0 1 0 14h-8" stroke="#598392" strokeWidth="4" fill="none" />
      </g>

      {/* person */}
      <g>
        <path d="M385 350c10-34 40-44 70-36 22 7 36 30 38 70l4 70h-92Z" fill="#598392" />
        <path d="M430 345c8 30 6 70-6 100" stroke="#124559" strokeWidth="5" fill="none" strokeLinecap="round" opacity=".5" />
        <path d="M410 392c-30 20-60 36-110 40" stroke="#598392" strokeWidth="24" strokeLinecap="round" fill="none" />
        <circle cx="296" cy="434" r="13" fill="#e8b996" />
        <path d="M400 470l-10 56h-8l8-50Z" fill="#01161e" />
        <rect x="386" y="466" width="96" height="30" rx="14" fill="#01161e" />
        <path d="M470 490l30 80" stroke="#01161e" strokeWidth="26" strokeLinecap="round" />
        <rect x="490" y="560" width="46" height="18" rx="9" fill="#eff6e0" />
        {/* head */}
        <rect x="408" y="296" width="26" height="30" rx="8" fill="#d9a07d" />
        <circle cx="425" cy="276" r="44" fill="#e8b996" />
        <path d="M382 270c-4-40 34-60 64-44 20 10 26 30 20 48-14-22-44-30-84-4Z" fill="#01161e" />
        <path d="M395 312c14 26 52 26 66 0-8 12-18 22-34 22s-26-10-32-22Z" fill="#01161e" />
        <circle cx="410" cy="282" r="12" fill="none" stroke="#01161e" strokeWidth="3" /><circle cx="444" cy="282" r="12" fill="none" stroke="#01161e" strokeWidth="3" /><path d="M422 282h10" stroke="#01161e" strokeWidth="3" />
        <circle cx="410" cy="283" r="3" fill="#01161e" /><circle cx="444" cy="283" r="3" fill="#01161e" />
      </g>
      </g>
    </svg>
  )
}

const input = 'w-full rounded-full border border-[#aec3b0] bg-white px-5 py-3.5 text-sm text-[#01161e] placeholder:text-[#598392]/70 focus:border-[#124559] focus:outline-none focus:ring-4 focus:ring-[#aec3b0]/40'

export default function Login() {
  const [params] = useSearchParams()
  const adminMode = params.get('mode') === 'admin'
  const [mode, setMode] = useState(params.get('mode') === 'register' ? 'register' : 'login')
  const [f, setF] = useState({ name: '', email: '', phone: '', password: '' })
  const [show, setShow] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const { user, login, register } = useAuth()
  const navigate = useNavigate()
  if (user) return <Navigate to={user.role === 'customer' ? '/app' : '/admin'} replace />

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      const u = mode === 'login' ? await login(f.email, f.password) : await register({ name: f.name, email: f.email, phone: f.phone || null, password: f.password })
      navigate(u.role === 'customer' ? '/app' : '/admin')
    } catch (ex) { setErr(errorMessage(ex)) } finally { setBusy(false) }
  }
  const title = adminMode ? 'Staff sign in' : mode === 'login' ? 'Welcome back' : 'Create account'

  return (
    <div className="min-h-full bg-[#eff6e0] p-3 md:p-5">
      <div className="relative mx-auto flex min-h-[calc(100vh-1.5rem)] max-w-[1280px] overflow-hidden rounded-[32px] bg-[#aec3b0] md:min-h-[calc(100vh-2.5rem)]">
        <div className="hidden md:block"><Scene /></div>

        <div className="absolute left-8 top-7 z-10 hidden items-center gap-2.5 md:flex">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-[#124559]"><svg viewBox="0 0 32 32" className="h-6 w-6"><path d="M9 11h10M9 16h14M9 21h8" stroke="#eff6e0" strokeWidth="2.6" strokeLinecap="round" /><circle cx="23" cy="21" r="2.6" fill="#aec3b0" /></svg></span>
          <span className="text-lg font-semibold tracking-tight text-[#01161e]">QueueLess</span>
        </div>
        <p className="absolute bottom-8 left-8 z-10 hidden max-w-xs text-2xl font-semibold leading-tight tracking-tight text-[#eff6e0] md:block">Know when to arrive.<br />Skip the wait.</p>

        <main className="relative z-10 flex w-full items-center justify-center p-3 md:ml-auto md:w-[46%] md:max-w-[560px] md:p-6">
          <form onSubmit={submit} className="w-full rounded-[28px] bg-white p-7 shadow-[0_24px_60px_-24px_rgba(1,22,30,0.45)] md:p-10" aria-labelledby="auth-title">
            <Link to="/" className="mb-6 flex items-center justify-center gap-2 md:hidden"><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#124559]"><svg viewBox="0 0 32 32" className="h-5 w-5"><path d="M9 11h10M9 16h14M9 21h8" stroke="#eff6e0" strokeWidth="2.6" strokeLinecap="round" /></svg></span><span className="font-semibold text-[#01161e]">QueueLess</span></Link>
            <h1 id="auth-title" className="text-center text-4xl font-semibold leading-[1.1] tracking-tight text-[#01161e]">{title}</h1>
            <p className="mt-2 text-center text-sm text-[#598392]">{adminMode ? 'Use the account issued by your administrator.' : mode === 'login' ? 'Sign in to see your queue.' : 'Join a queue in under a minute.'}</p>

            <div className="mt-7 space-y-3.5">
              {err && <div role="alert" className="flex items-start gap-2 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{err}</div>}
              {mode === 'register' && !adminMode && <input className={input} required placeholder="Full name" aria-label="Full name" value={f.name} onChange={set('name')} autoComplete="name" />}
              <input className={input} type="email" required placeholder="Email address" aria-label="Email address" value={f.email} onChange={set('email')} autoComplete="email" />
              {mode === 'register' && !adminMode && <input className={input} type="tel" placeholder="Phone (optional)" aria-label="Phone" value={f.phone} onChange={set('phone')} autoComplete="tel" />}
              <div className="relative">
                <input className={`${input} pr-12`} type={show ? 'text' : 'password'} required minLength={mode === 'register' ? 8 : 1} placeholder={mode === 'register' ? 'Password (8+ characters)' : 'Password'} aria-label="Password" value={f.password} onChange={set('password')} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
                <button type="button" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'} className="absolute right-4 top-1/2 -translate-y-1/2 text-[#598392] hover:text-[#124559]">{show ? <EyeOff className="h-[18px] w-[18px]" /> : <Eye className="h-[18px] w-[18px]" />}</button>
              </div>
              <button type="submit" disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-full bg-[#124559] py-3.5 text-sm font-semibold text-[#eff6e0] shadow-md transition-colors hover:bg-[#01161e] focus-visible:ring-4 focus-visible:ring-[#aec3b0]">
                {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}{mode === 'login' ? 'Sign in' : 'Create account'}
              </button>
            </div>

            {import.meta.env.DEV && (
              <div className="mt-6 border-t border-[#aec3b0]/60 pt-4 text-center">
                <p className="text-[11px] uppercase tracking-wider text-[#598392]">Local demo accounts</p>
                <div className="mt-2 flex justify-center gap-2">
                  {[['Admin', 'admin@queueless.demo'], ['Staff', 'staff1@queueless.demo'], ['Customer', 'customer1@queueless.demo']].map(([l, em]) => (
                    <button key={l} type="button" onClick={() => { setMode('login'); setF({ ...f, email: em, password: 'Demo@12345' }) }} className="rounded-full bg-[#eff6e0] px-3.5 py-1.5 text-xs font-medium text-[#124559] hover:bg-[#aec3b0]/60">{l}</button>
                  ))}
                </div>
              </div>
            )}

            {mode === 'register' && <p className="mt-5 text-center text-xs text-[#598392]">By creating an account you agree to the service terms and privacy policy.</p>}
            {!adminMode && (
              <p className="mt-6 text-center text-sm text-[#598392]">
                {mode === 'login' ? 'New here?' : 'Have an account?'}{' '}
                <button type="button" className="font-semibold text-[#124559] hover:underline" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setErr('') }}>{mode === 'login' ? 'Create account' : 'Log in'}</button>
              </p>
            )}
          </form>
        </main>
      </div>
    </div>
  )
}
