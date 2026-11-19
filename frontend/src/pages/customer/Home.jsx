import { Link } from 'react-router-dom'
import { ArrowRight, Clock, Ticket, TicketPlus } from 'lucide-react'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { useLiveEvent, usePoll } from '../../lib/live'
import { useLocations } from '../../lib/location'
import { time, mins } from '../../lib/format'
import { Card, CardTitle, Empty, EstimateBadge, PageHeader, Spinner, StatusBadge } from '../../components/ui'

export function TokenSummary({ t }) {
  const { nameOf } = useLocations()
  const est = t.estimate
  return (
    <Link to={`/app/token/${t.token_id}`} className="block rounded-3xl bg-white p-5 shadow-card ring-1 ring-black/[0.03] transition hover:ring-brand-200">
      <div className="flex items-start justify-between">
        <div><p className="text-xs text-muted">{t.service.service_name}{nameOf(t.service.location_id) ? ` · ${nameOf(t.service.location_id)}` : ''}</p><p className="mt-1 text-4xl font-semibold tracking-tight">{t.token_label}</p></div>
        <StatusBadge status={t.status} />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div><p className="text-xs text-muted">Ahead of you</p><p className="font-semibold">{t.customers_ahead ?? '—'}</p></div>
        <div><p className="text-xs text-muted">Est. wait</p><p className="font-semibold">{est?.wait_minutes != null ? mins(est.wait_minutes) : '—'}</p></div>
        <div><p className="text-xs text-muted">Arrive around</p><p className="font-semibold">{t.arrival_window ? (t.arrival_window.arrive_now ? 'Now' : time(t.arrival_window.recommended_arrival)) : t.counter?.counter_name || '—'}</p></div>
      </div>
      <div className="mt-3 flex items-center justify-between"><EstimateBadge estimate={est} /><span className="inline-flex items-center gap-1 text-sm font-medium text-brand-600">Track live <ArrowRight className="h-4 w-4" aria-hidden /></span></div>
    </Link>
  )
}

export default function CustomerHome() {
  const { user } = useAuth()
  const mine = usePoll(() => api.get('/queue/mine?active_only=true').then((r) => r.data), [], 30000)
  const services = usePoll(() => api.get('/services').then((r) => r.data), [], 30000)
  useLiveEvent((m) => { if (m.type === 'token_update') mine.reload() })

  return (
    <>
      <PageHeader title={`Hello, ${user.name.split(' ')[0]}`} sub="Here is where you stand right now." actions={<Link to="/app/join" className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-700"><TicketPlus className="h-4 w-4" aria-hidden />Join a queue</Link>} />
      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-slate-600">Your active tokens</h2>
          {mine.loading ? <Spinner /> : mine.data?.length ? mine.data.map((t) => <TokenSummary key={t.token_id} t={t} />) : (
            <Card><Empty icon={Ticket} title="No active token">Pick a service and join the queue remotely. We will tell you when to leave for the counter.</Empty></Card>
          )}
        </div>
        <Card>
          <CardTitle sub="Live from the service centre">Current conditions</CardTitle>
          {services.loading ? <Spinner /> : (
            <ul className="divide-y divide-line">
              {services.data?.map((s) => (
                <li key={s.service.service_id} className="flex items-center justify-between gap-3 py-3">
                  <div><p className="text-sm font-medium">{s.service.service_name}</p><p className="text-xs text-muted">{s.queue_length} waiting · {s.active_counters} counter{s.active_counters === 1 ? '' : 's'} open</p></div>
                  <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2.5 py-1 text-xs font-medium"><Clock className="h-3.5 w-3.5 text-muted" aria-hidden />{s.estimate.wait_minutes != null ? `~${Math.round(s.estimate.wait_minutes)} min` : 'Closed'}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  )
}
