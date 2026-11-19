import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, CheckCircle2, Clock, DoorOpen, Hourglass, Sparkles, TrendingUp, UserCheck, Users } from 'lucide-react'
import { api, errorMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { applyAction } from '../../lib/actions'
import { useDebounced, useLiveEvent, usePoll } from '../../lib/live'
import { mins } from '../../lib/format'
import { Badge, Button, Card, CardTitle, DemoBanner, Empty, Gauge, PageHeader, Spinner, Stat, StatusBadge, useToast } from '../../components/ui'

export const C = { blue: '#124559', violet: '#598392', amber: '#d98b1f', green: '#0f9d6b', slate: '#aec3b0' }
const tip = { contentStyle: { borderRadius: 14, border: '1px solid #dbe5d6', boxShadow: '0 12px 28px -14px rgba(1,22,30,.35)', fontSize: 12 } }
const LEVEL = { low: [1, 'green', 'Low congestion'], moderate: [2, 'amber', 'Moderate'], high: [4, 'amber', 'High congestion'], critical: [5, 'red', 'Critical'] }

export const ChartEmpty = () => <Empty title="No data yet">Charts fill in as customers are served.</Empty>
const Legend_ = ({ items }) => (
  <div className="flex flex-wrap gap-4 text-[13px] text-muted">
    {items.map(([c, l, dashed]) => <span key={l} className="inline-flex items-center gap-2"><span className="w-[18px]" style={dashed ? { borderTop: `3px dashed ${c}` } : { height: 4, borderRadius: 4, background: c }} />{l}</span>)}
  </div>
)

export default function Overview() {
  const { user } = useAuth()
  const toast = useToast()
  const ov = usePoll(() => api.get('/analytics/overview').then((r) => r.data), [], 15000)
  const hourly = usePoll(() => api.get('/analytics/traffic?granularity=hour').then((r) => r.data), [], 60000)
  const daily = usePoll(() => api.get('/analytics/traffic?granularity=day&days=14').then((r) => r.data), [], 120000)
  const wait = usePoll(() => api.get('/analytics/waiting-time?days=14').then((r) => r.data), [], 60000)
  const counters = usePoll(() => api.get('/analytics/counter-performance?days=14').then((r) => r.data), [], 120000)
  const pva = usePoll(() => api.get('/analytics/predicted-vs-actual-arrivals').then((r) => r.data), [], 120000)
  const alerts = usePoll(() => api.get('/admin/alerts').then((r) => r.data), [], 20000)
  const services = usePoll(() => api.get('/services').then((r) => r.data), [], 20000)
  const queue = usePoll(() => api.get('/admin/queue?page_size=200').then((r) => r.data), [], 15000)
  const refreshLive = useDebounced(() => { ov.reload(); alerts.reload(); hourly.reload(); services.reload(); queue.reload() })
  useLiveEvent((m) => { if (m.type === 'queue_changed') refreshLive() })

  const o = ov.data
  if (ov.loading) return <Spinner />
  if (!o) return <Empty icon={AlertTriangle} title="Could not load the dashboard">Check that the API is running and you are signed in as staff.</Empty>

  const [segments, tone, levelLabel] = LEVEL[o.congestion_level]
  const activeCounters = counters.data?.filter((c) => c.status !== 'closed' || c.served) || []
  const avgUtil = activeCounters.length ? activeCounters.reduce((s, c) => s + c.utilization, 0) / activeCounters.length : 0
  const alertList = alerts.data?.alerts || []
  const topAction = alertList.find((a) => a.action)
  const waits = (services.data || []).map((s) => s.estimate.wait_minutes).filter((v) => v != null)
  const longest = waits.length ? Math.max(...waits) : null
  const spark = (rows, key) => (rows || []).slice(-10).map((r) => r[key]).filter((v) => v != null)
  const prevWait = wait.data?.daily?.length > 1 ? wait.data.daily[wait.data.daily.length - 2].avg_wait : null
  const waitDelta = o.avg_wait_minutes != null && prevWait != null ? Math.round(o.avg_wait_minutes - prevWait) : null
  const maxQ = Math.max(1, ...(services.data || []).map((s) => s.queue_length))
  const nextUp = (queue.data?.items || []).filter((t) => ['booked', 'confirmed', 'waiting', 'approaching'].includes(t.status)).sort((a, b) => (a.queue_position ?? 99) - (b.queue_position ?? 99)).slice(0, 5)

  // today's real arrivals per hour (area) + the stored model forecast where it exists (dashed line)
  const byLabel = {}
  ;(hourly.data?.series || []).forEach((r) => { byLabel[r.label] = { label: r.label, actual: r.arrivals } })
  ;(pva.data || []).forEach((r) => { byLabel[r.label] = { ...(byLabel[r.label] || { label: r.label }), predicted: r.predicted } })
  const arrivalsData = Object.values(byLabel).sort((a, b) => a.label.localeCompare(b.label))

  const apply = async (a) => { try { await applyAction(a.action); toast(`${a.action.label}: done`); alerts.reload(); ov.reload(); services.reload() } catch (e) { toast(errorMessage(e), 'error') } }
  const call = async (t) => { try { await api.post(`/admin/queue/${t.token_id}/call`, {}); toast(`Called ${t.token_label}`); queue.reload(); ov.reload() } catch (e) { toast(errorMessage(e), 'error') } }
  const today = new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <>
      <PageHeader eyebrow={today} title="Operational overview" badge={o.demo_data_present && o.demo_mode ? <Badge tone="amber">Demo data</Badge> : null} />
      <DemoBanner show={o.demo_data_present && o.demo_mode} />

      {/* hero row */}
      <div className="grid gap-5 xl:grid-cols-2">
        <section className="flex flex-col gap-5 rounded-[28px] p-7 text-brand-50" style={{ background: 'radial-gradient(120% 90% at 100% 0%, #2a6177 0%, #124559 55%, #0b3142 100%)' }}>
          <div className="flex items-center justify-between gap-3">
            <span className="text-[13px] font-semibold uppercase tracking-[0.1em] text-brand-200">Right now</span>
            <span className={`inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[13px] font-semibold ${tone === 'green' ? 'bg-[#dcefe4] text-[#0b5a3c]' : tone === 'red' ? 'bg-[#f9dcd8] text-[#8f1a10]' : 'bg-[#f6d98f] text-[#4a2a02]'}`}>{tone !== 'green' && <AlertTriangle className="h-3.5 w-3.5" aria-hidden />}{levelLabel}</span>
          </div>
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div className="flex items-baseline gap-3.5"><span className="font-display text-[84px] font-semibold leading-[0.9] tracking-tighter">{o.currently_waiting}</span><span className="text-base leading-snug text-brand-200">customers<br />waiting</span></div>
            <div className="min-w-[190px]">
              <p className="mb-2 text-xs text-brand-200">Congestion · {o.currently_serving} being served</p>
              <div className="grid grid-cols-5 gap-1.5" role="img" aria-label={`Congestion level ${segments} of 5`}>
                {[1, 2, 3, 4, 5].map((n) => <span key={n} className={`h-2.5 rounded-full ${n <= segments ? (n === 4 || n === 5 ? 'bg-[#f6d98f]' : 'bg-brand-200') : 'bg-brand-50/20'}`} />)}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-[18px] bg-brand-50/10 p-4"><p className="text-xs text-brand-200">Longest wait for a new customer</p><p className="mt-1 font-display text-2xl font-semibold">{longest != null ? `${Math.round(longest)} min` : '—'}</p><p className="text-xs text-brand-200">per service estimate</p></div>
            <div className="rounded-[18px] bg-brand-50/10 p-4"><p className="text-xs text-brand-200">Counters open</p><p className="mt-1 font-display text-2xl font-semibold">{o.active_counters} / {o.total_counters}</p><p className="text-xs text-brand-200">{o.total_counters - o.active_counters} closed</p></div>
            <div className="rounded-[18px] bg-brand-50/10 p-4"><p className="text-xs text-brand-200">Arrivals, next hour</p><p className="mt-1 font-display text-2xl font-semibold">≈ {Math.round(o.predicted_arrivals_next_hour)}</p><p className="text-xs text-brand-200">{o.predicted_arrivals_method === 'ml' ? 'ML forecast' : 'Historical average'}</p></div>
          </div>
          <div className="flex flex-wrap items-center gap-4 rounded-[20px] bg-brand-50 p-4 text-ink">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[14px] bg-brand-600 text-brand-50"><Sparkles className="h-5 w-5" aria-hidden /></span>
            <p className="min-w-[220px] flex-1 text-sm leading-relaxed">{topAction ? <><strong className="font-semibold">{topAction.message}</strong> {topAction.recommendation}</> : alertList.length ? alertList[0].message : 'All clear — no thresholds are exceeded right now.'}</p>
            {topAction && user.role === 'admin' && <Button onClick={() => apply(topAction)}>{topAction.action.label}</Button>}
            {topAction && user.role !== 'admin' && <Link to="/admin/forecast" className="text-sm font-semibold text-brand-600 underline">Details</Link>}
          </div>
        </section>

        <Card className="flex flex-col gap-4 !p-7">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h3 className="font-display text-xl font-semibold tracking-tight">Arrivals vs forecast</h3><p className="mt-1 text-[13px] text-muted">Customers joining per hour</p></div>
            <Legend_ items={[[C.blue, 'Actual'], [C.violet, 'Forecast (ML)', true]]} />
          </div>
          <div className="h-[290px]">{arrivalsData.length ? (
            <ResponsiveContainer><ComposedChart data={arrivalsData}><defs><linearGradient id="arr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={C.blue} stopOpacity={0.28} /><stop offset="1" stopColor={C.blue} stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} width={28} /><Tooltip {...tip} />
              <Area type="monotone" dataKey="actual" name="Actual" stroke={C.blue} strokeWidth={3.5} fill="url(#arr)" connectNulls isAnimationActive={false} dot={{ r: 4, fill: '#fff', stroke: C.blue, strokeWidth: 3 }} />
              <Line type="monotone" dataKey="predicted" name="Forecast" stroke={C.violet} strokeDasharray="7 6" strokeWidth={3} connectNulls isAnimationActive={false} dot={{ r: 3, fill: C.violet }} /></ComposedChart></ResponsiveContainer>
          ) : <ChartEmpty />}</div>
          <p className="rounded-2xl bg-brand-50 px-4 py-3 text-[13px] leading-relaxed text-muted">Forecast accuracy is measured on simulated data until real services are completed. Queue order never depends on a prediction.</p>
        </Card>
      </div>

      {/* KPIs */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <Stat icon={Users} label="Customers today" value={o.customers_today} spark={spark(daily.data?.series, 'arrivals')} />
        <Stat icon={Hourglass} label="Waiting now" value={o.currently_waiting} unit={`${o.currently_serving} in service`} delta="live" />
        <Stat icon={Clock} label="Avg wait" value={o.avg_wait_minutes != null ? Math.round(o.avg_wait_minutes) : null} unit="min" delta={waitDelta != null ? `${waitDelta > 0 ? '+' : waitDelta < 0 ? '−' : ''}${Math.abs(waitDelta)} min` : null} deltaTone={waitDelta != null && waitDelta <= 0 ? 'green' : 'amber'} spark={spark(wait.data?.daily, 'avg_wait')} />
        <Stat icon={UserCheck} label="Avg service" value={o.avg_service_minutes != null ? Math.round(o.avg_service_minutes) : null} unit="min" hint={`${o.served_today} served today`} spark={spark(wait.data?.daily, 'avg_service')} />
        <Stat icon={DoorOpen} label="Active counters" value={`${o.active_counters}/${o.total_counters}`} unit="open" />
        <Stat icon={TrendingUp} label="Arrivals next hour" value={`≈ ${Math.round(o.predicted_arrivals_next_hour)}`} delta={o.predicted_arrivals_method === 'ml' ? 'ML' : 'avg'} />
      </div>

      {/* charts */}
      <div className="mt-5 grid gap-5 xl:grid-cols-3">
        <Card>
          <CardTitle sub="Daily average, last 14 days (minutes)">Waiting-time trend</CardTitle>
          <div className="h-56">{wait.data?.daily.length ? (
            <ResponsiveContainer><LineChart data={wait.data.daily}><CartesianGrid vertical={false} /><XAxis dataKey="label" tickFormatter={(v) => v.slice(5)} tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} width={28} /><Tooltip {...tip} />
              <Line type="monotone" dataKey="avg_wait" name="Avg wait" stroke={C.blue} strokeWidth={3.2} dot={false} /><Line type="monotone" dataKey="avg_service" name="Avg service" stroke={C.slate} strokeWidth={3.2} dot={false} /></LineChart></ResponsiveContainer>
          ) : <ChartEmpty />}</div>
          <div className="mt-3"><Legend_ items={[[C.blue, 'Avg wait'], [C.slate, 'Avg service']]} /></div>
        </Card>
        <Card>
          <CardTitle sub="Last 14 days">Counter utilization</CardTitle>
          <div className="flex flex-wrap items-center gap-5"><Gauge value={avgUtil} label="Average utilization" /><p className="min-w-[120px] flex-1 text-[13px] leading-relaxed text-muted">Target is 85%. The busiest counters carry the longest transactions.</p></div>
          <ul className="mt-4 space-y-3">
            {counters.data?.map((c) => (
              <li key={c.counter_id} className="grid grid-cols-[84px_1fr_42px] items-center gap-3 text-[13px]">
                <span className="flex items-center gap-2 font-medium"><span className={`h-2 w-2 rounded-full ${c.status === 'open' ? 'bg-brand-600' : 'bg-brand-200'}`} />{c.counter_name}</span>
                <span className="h-2.5 overflow-hidden rounded-full bg-slate-100"><span className="block h-full rounded-full bg-brand-600" style={{ width: `${Math.round(c.utilization * 100)}%` }} /></span>
                <span className="text-right font-semibold">{Math.round(c.utilization * 100)}%</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardTitle sub="Waiting now, with the estimate a new customer would see">Queue by service</CardTitle>
          <ul className="space-y-4">
            {services.data?.map((s, i) => (
              <li key={s.service.service_id}>
                <div className="flex items-baseline justify-between gap-2"><span className="text-sm font-semibold">{s.service.service_name}</span><span className="text-[13px] text-muted">{s.queue_length} waiting · {s.estimate.wait_minutes != null ? `~${Math.round(s.estimate.wait_minutes)} min` : 'no counter'}</span></div>
                <div className="mt-2 h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full" style={{ width: `${Math.max(4, (s.queue_length / maxQ) * 100)}%`, background: i % 2 ? C.violet : C.blue }} /></div>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* alerts + next up */}
      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Card>
          <CardTitle sub="You decide what to apply. Every change is audited." right={<Badge tone={alertList.length ? 'amber' : 'green'}>{alertList.length} active</Badge>}>Alerts &amp; actions</CardTitle>
          {alertList.length ? (
            <ul className="space-y-3">
              {alertList.slice(0, 4).map((a, i) => (
                <li key={i} className="flex flex-wrap items-center gap-3.5 rounded-[20px] border border-[#e1ebd8] bg-slate-50 p-4">
                  <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-[14px] ${a.severity === 'critical' ? 'bg-[#f9dcd8] text-[#8f1a10]' : 'bg-[#fbecc8] text-[#7a4205]'}`}><AlertTriangle className="h-5 w-5" aria-hidden /></span>
                  <div className="min-w-[200px] flex-1"><p className="text-sm font-semibold leading-snug">{a.message}</p><p className="mt-0.5 text-[13px] text-muted">{a.recommendation}</p></div>
                  {a.action && user.role === 'admin' && <Button size="sm" onClick={() => apply(a)}>{a.action.label}</Button>}
                </li>
              ))}
            </ul>
          ) : <Empty icon={CheckCircle2} title="All clear">No congestion alerts right now.</Empty>}
        </Card>
        <Card>
          <CardTitle sub="Priority first, then joining time" right={<Link to="/admin/queue" className="text-[13px] font-semibold text-brand-600 underline">Open live queue</Link>}>Next in line</CardTitle>
          {nextUp.length ? (
            <ul>
              {nextUp.map((t) => (
                <li key={t.token_id} className="grid grid-cols-[64px_1fr_auto_auto] items-center gap-3.5 border-t border-line py-3">
                  <span className="font-display text-lg font-semibold">{t.token_label}</span>
                  <span className="min-w-0"><span className="block truncate text-sm font-medium">{t.customer_name}</span><span className="text-xs text-muted">{t.service_name} · waited {mins(t.waited_minutes)}</span></span>
                  <StatusBadge status={t.status} />
                  <Button size="sm" variant="ghost" onClick={() => call(t)}>Call</Button>
                </li>
              ))}
            </ul>
          ) : <Empty title="Nobody is waiting">New tokens appear here instantly.</Empty>}
        </Card>
      </div>
    </>
  )
}
