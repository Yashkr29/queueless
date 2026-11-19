import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, CheckCircle2, TrendingUp } from 'lucide-react'
import { api, errorMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { applyAction } from '../../lib/actions'
import { useLiveEvent, usePoll } from '../../lib/live'
import { Badge, Button, Card, CardTitle, Empty, ErrorBox, PageHeader, Select, Spinner, useToast } from '../../components/ui'
import { C } from './Overview'

export default function Forecast() {
  const { user } = useAuth()
  const toast = useToast()
  const services = usePoll(() => api.get('/services').then((r) => r.data), [])
  const [sid, setSid] = useState('')
  const serviceId = sid || services.data?.[0]?.service.service_id
  const demand = usePoll(() => (serviceId ? api.get(`/predictions/demand/${serviceId}`).then((r) => r.data) : Promise.resolve(null)), [serviceId], 60000)
  const alerts = usePoll(() => api.get('/admin/alerts').then((r) => r.data), [], 20000)
  const [err, setErr] = useState('')
  useLiveEvent((m) => { if (m.type === 'queue_changed') alerts.reload() })

  const apply = async (a) => { setErr(''); try { await applyAction(a.action); toast('Applied — estimates recalculated'); alerts.reload(); demand.reload() } catch (e) { setErr(errorMessage(e)) } }
  const d = demand.data
  const ml = d?.forecasts.some((f) => f.method === 'ml')

  return (
    <>
      <PageHeader title="Forecast & congestion alerts" sub="What the demand model expects, and what the rules engine suggests you do about it." actions={
        <Select className="!w-auto" aria-label="Service" value={serviceId ?? ''} onChange={(e) => setSid(e.target.value)}>{services.data?.map((s) => <option key={s.service.service_id} value={s.service.service_id}>{s.service.service_name}</option>)}</Select>} />
      {err && <div className="mb-4"><ErrorBox>{err}</ErrorBox></div>}

      <div className="grid gap-5 xl:grid-cols-[1.2fr_1fr]">
        <div className="space-y-5">
          <Card>
            <CardTitle sub="Expected customer arrivals starting from the current half-hour" right={d && <Badge tone={ml ? 'blue' : 'slate'}>{ml ? 'ML forecast' : 'Historical average (non-ML)'}</Badge>}>Demand forecast</CardTitle>
            {demand.loading ? <Spinner /> : d ? (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  {d.forecasts.map((f) => (
                    <div key={f.horizon_minutes} className={`rounded-2xl p-4 ${f.potential_congestion ? 'bg-amber-50' : 'bg-surface'}`}>
                      <p className="text-xs text-muted">Next {f.horizon_minutes >= 60 ? `${f.horizon_minutes / 60} h` : `${f.horizon_minutes} min`}</p>
                      <p className="mt-1 text-3xl font-semibold">{f.predicted_arrivals.toFixed(1)}<span className="ml-1 text-sm font-normal text-muted">arrivals</span></p>
                      <p className="mt-2 text-xs text-muted">Workload ≈ {Math.round(f.expected_workload_minutes)} counter-min<br />Capacity {f.capacity_minutes} counter-min</p>
                      {f.potential_congestion && <Badge tone="amber" className="mt-2">Potential congestion</Badge>}
                    </div>
                  ))}
                </div>
                <h4 className="mb-2 mt-6 text-sm font-semibold">Expected peak hours (same weekday, last 4 weeks)</h4>
                {d.expected_peak_hours.length ? (
                  <div className="h-44"><ResponsiveContainer><BarChart data={d.expected_peak_hours.map((p) => ({ label: `${String(p.hour).padStart(2, '0')}:00`, avg: p.avg_arrivals }))}><CartesianGrid vertical={false} /><XAxis dataKey="label" tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} width={28} /><Tooltip cursor={{ fill: '#eef4e6' }} contentStyle={{ borderRadius: 12, fontSize: 12 }} /><Bar dataKey="avg" name="Avg arrivals / hour" fill={C.violet} radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer></div>
                ) : <p className="text-sm text-muted">Not enough history yet.</p>}
                {d.preparation.length > 0 && <div className="mt-4 rounded-2xl bg-amber-50 p-4 text-sm text-amber-900"><b>Prepare:</b> {d.preparation.join(' ')}</div>}
              </>
            ) : <Empty icon={TrendingUp} title="Pick a service" />}
          </Card>
        </div>

        <Card>
          <CardTitle sub="Thresholds are set in Settings. You decide what to apply." right={<Badge tone={alerts.data?.alerts.length ? 'amber' : 'green'}>{alerts.data?.alerts.length || 0} active</Badge>}>Alerts & actions</CardTitle>
          {alerts.loading ? <Spinner /> : alerts.data?.alerts.length ? (
            <ul className="space-y-3">
              {alerts.data.alerts.map((a, i) => (
                <li key={i} className="rounded-2xl bg-surface p-4">
                  <div className="flex items-start gap-2.5">
                    <AlertTriangle className={`mt-0.5 h-4 w-4 shrink-0 ${a.severity === 'critical' ? 'text-red-500' : 'text-amber-500'}`} aria-hidden />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2"><Badge tone={a.severity === 'critical' ? 'red' : 'amber'}>{a.severity}</Badge><span className="text-xs text-muted">{a.type.replaceAll('_', ' ')}</span></div>
                      <p className="mt-1.5 text-sm font-medium">{a.message}</p><p className="mt-1 text-sm text-slate-600">→ {a.recommendation}</p>
                      {a.action && user.role === 'admin' && <Button size="sm" className="mt-3" onClick={() => apply(a)}>{a.action.label}</Button>}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : <Empty icon={CheckCircle2} title="All clear">No thresholds are currently exceeded.</Empty>}
        </Card>
      </div>
    </>
  )
}
