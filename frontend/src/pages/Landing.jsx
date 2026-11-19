import { Link, Navigate } from 'react-router-dom'
import { ArrowRight, BellRing, Clock3, LineChart, ShieldCheck, Sparkles, Users } from 'lucide-react'
import { Logo } from '../components/Shell'
import { useAuth } from '../lib/auth'

const FEATURES = [
  { icon: Clock3, title: 'Honest wait times', text: 'A trained model estimates your wait and shows a range, not a promise. If the model is offline we say so and fall back to a simple estimate.' },
  { icon: BellRing, title: 'Arrive at the right time', text: 'Get a recommended arrival window based on your predicted turn, so you spend your wait anywhere but the waiting room.' },
  { icon: LineChart, title: 'Forecast the rush', text: 'Demand forecasts for the next 30, 60 and 120 minutes tell staff when to open another counter — before the queue builds.' },
  { icon: ShieldCheck, title: 'Fair by design', text: 'Queue order follows priority rules, never a prediction. Every manual override is recorded for audit.' },
]

export default function Landing() {
  const { user } = useAuth()
  if (user) return <Navigate to={user.role === 'customer' ? '/app' : '/admin'} replace />
  return (
    <div className="min-h-full bg-surface">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <Logo />
        <nav className="flex items-center gap-2 text-sm font-medium">
          <Link to="/login?mode=admin" className="rounded-xl px-3 py-2 text-slate-600 hover:bg-white">Staff & admin</Link>
          <Link to="/login" className="rounded-xl bg-brand-600 px-4 py-2 text-white shadow-sm hover:bg-brand-700">Sign in</Link>
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-10 px-5 pb-14 pt-8 md:grid-cols-[1.1fr_1fr] md:pt-14">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-medium text-brand-700 shadow-card"><Sparkles className="h-3.5 w-3.5" aria-hidden />Predictive queue management</span>
          <h1 className="mt-5 text-4xl font-semibold leading-[1.08] tracking-tight md:text-6xl">Know when to arrive.<br /><span className="text-brand-600">Skip the wait.</span></h1>
          <p className="mt-5 max-w-lg text-lg text-slate-600">Join the queue from anywhere, see when you will really be served, and walk in just in time. Service teams see congestion coming and act before it happens.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/login?mode=register" className="inline-flex items-center gap-2 rounded-2xl bg-brand-600 px-6 py-3.5 font-medium text-white shadow-md hover:bg-brand-700">Get a token <ArrowRight className="h-4 w-4" aria-hidden /></Link>
            <Link to="/login?mode=admin" className="inline-flex items-center gap-2 rounded-2xl bg-white px-6 py-3.5 font-medium text-ink ring-1 ring-line hover:bg-slate-50"><Users className="h-4 w-4" aria-hidden />Open the dashboard</Link>
          </div>
        </div>

        {/* Product preview built from the same UI primitives, not an image */}
        <div className="relative" aria-hidden>
          <div className="rounded-[32px] bg-white p-6 shadow-card ring-1 ring-black/[0.03]">
            <div className="flex items-center justify-between"><span className="text-sm text-muted">Your token</span><span className="rounded-full bg-brand-200/40 px-2.5 py-1 text-xs font-medium text-brand-600">Approaching turn</span></div>
            <p className="mt-2 text-6xl font-semibold tracking-tight">D-024</p>
            <div className="mt-5 grid grid-cols-3 gap-3 text-center">
              {[['Ahead', '3'], ['Est. wait', '22 min'], ['Range', '17–27']].map(([k, v]) => (
                <div key={k} className="rounded-2xl bg-surface p-3"><p className="text-xs text-muted">{k}</p><p className="mt-1 text-lg font-semibold">{v}</p></div>
              ))}
            </div>
            <div className="mt-4 rounded-2xl bg-brand-50 p-4"><p className="text-xs font-medium text-brand-700">Recommended arrival</p><p className="mt-1 text-2xl font-semibold text-brand-700">12:25 PM</p><p className="text-xs text-brand-700/70">Window 12:20 – 12:35 PM</p></div>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-4 px-5 pb-20 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map(({ icon: Icon, title, text }) => (
          <div key={title} className="rounded-3xl bg-white p-5 shadow-card">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-brand-50 text-brand-600"><Icon className="h-5 w-5" aria-hidden /></span>
            <h3 className="mt-4 font-semibold">{title}</h3><p className="mt-1.5 text-sm text-slate-600">{text}</p>
          </div>
        ))}
      </section>
      <footer className="border-t border-line py-6 text-center text-xs text-muted">QueueLess — predictions are estimates, not guarantees.</footer>
    </div>
  )
}
