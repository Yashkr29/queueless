import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { Info } from 'lucide-react'
import { api } from '../../lib/api'
import { usePoll } from '../../lib/live'
import { pct } from '../../lib/format'
import { Badge, Card, CardTitle, DemoBanner, Empty, PageHeader, Spinner } from '../../components/ui'
import { C } from './Overview'

const Metric = ({ label, value, unit, hint }) => (
  <div className="rounded-2xl bg-surface p-4"><p className="text-xs text-muted">{label}</p><p className="mt-1 text-2xl font-semibold">{value ?? '—'}{value != null && unit && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}</p>{hint && <p className="mt-1 text-xs text-muted">{hint}</p>}</div>
)

export default function MLMonitor() {
  const { data: m, loading } = usePoll(() => api.get('/analytics/ml-monitoring?days=30').then((r) => r.data), [], 120000)
  if (loading) return <Spinner />
  if (!m) return <Empty title="Unavailable" />
  const w = m.wait_model, dm = m.demand_model, live = m.live_vs_actual.all, real = m.live_vs_actual.real_only
  const hasDemo = !!m.live_vs_actual.demo_only

  return (
    <>
      <PageHeader title="ML monitoring" sub="Predicted vs actual outcomes, model versions and drift." />
      <DemoBanner show={hasDemo} />
      <div className="mb-5 flex items-start gap-2 rounded-2xl bg-brand-50 px-4 py-3 text-sm text-brand-700"><Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /><span>{m.note}</span></div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardTitle sub="Waiting-time model" right={w ? <Badge tone="amber">Trained on {w.trained_on === 'synthetic' ? 'simulated' : 'real'} data</Badge> : <Badge>No model — fallback in use</Badge>}>Model registry</CardTitle>
          {w ? (<>
            <p className="break-all text-sm"><b>{w.algorithm}</b> <span className="text-muted">· {w.version}</span></p>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label="Test MAE" value={w.metrics.test.MAE.toFixed(2)} unit="min" hint="simulated" /><Metric label="Test RMSE" value={w.metrics.test.RMSE.toFixed(2)} unit="min" hint="simulated" />
              <Metric label="Test R²" value={w.metrics.test.R2.toFixed(2)} hint="simulated" /><Metric label="80% interval coverage" value={pct(w.metrics.test_interval_coverage)} hint="simulated" />
            </div></>) : <p className="text-sm text-muted">Run <code>python ml/train_wait_time.py</code> to create a model. Until then every estimate is labelled as a non-ML fallback.</p>}
          {dm && <p className="mt-4 text-xs text-muted">Demand model <b>{dm.version}</b>: {Object.entries(dm.algorithms).map(([h, a]) => `${h}min ${a}`).join(' · ')}. Simulated WAPE {Object.entries(dm.metrics).map(([h, x]) => `${h}min ${pct(x.WAPE)}`).join(', ')}.</p>}
        </Card>

        <Card>
          <CardTitle sub="First prediction made at joining vs actual wait, last 30 days" right={m.drift && <Badge tone={m.drift.flag ? 'red' : 'green'}>{m.drift.flag ? 'Drift detected' : 'No drift'}</Badge>}>Live accuracy</CardTitle>
          {live ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Metric label="MAE" value={live.mae} unit="min" /><Metric label="RMSE" value={live.rmse} unit="min" /><Metric label="Bias" value={live.bias} unit="min" hint="+ = over-estimates" /><Metric label="In range" value={pct(live.interval_coverage)} hint={`n = ${live.n}`} />
            </div>) : <p className="text-sm text-muted">No completed services with predictions yet.</p>}
          <p className="mt-3 text-xs text-muted">{real ? `Real customers only: MAE ${real.mae} min over ${real.n} services.` : 'Real-customer accuracy: not available yet — no real services have been completed. Figures above are demo data.'}</p>
          {m.drift && <p className="mt-1 text-xs text-muted">Drift check: last 7 days MAE {m.drift.recent_mae} vs prior 7 days {m.drift.prior_mae} (ratio {m.drift.ratio}; flagged above 1.2).</p>}
        </Card>

        <Card>
          <CardTitle sub="Each dot is one served customer (latest 300)">Predicted vs actual wait</CardTitle>
          <div className="h-72">{m.scatter.length ? (
            <ResponsiveContainer><ScatterChart margin={{ left: 0, right: 8 }}><CartesianGrid /><XAxis type="number" dataKey="actual" name="Actual" unit=" min" tickLine={false} /><YAxis type="number" dataKey="predicted" name="Predicted" unit=" min" tickLine={false} width={44} /><Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ borderRadius: 12, fontSize: 12 }} />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 90, y: 90 }]} stroke={C.slate} strokeDasharray="4 4" /><Scatter data={m.scatter} fill={C.blue} fillOpacity={0.45} /></ScatterChart></ResponsiveContainer>
          ) : <Empty title="No pairs yet" />}</div>
        </Card>
        <Card>
          <CardTitle sub="Mean absolute error per day, minutes">Prediction error over time</CardTitle>
          <div className="h-72">{m.daily_mae.length ? (
            <ResponsiveContainer><LineChart data={m.daily_mae}><CartesianGrid vertical={false} /><XAxis dataKey="label" tickFormatter={(v) => v.slice(5)} tickLine={false} axisLine={false} /><YAxis tickLine={false} axisLine={false} width={28} /><Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} /><Line type="monotone" dataKey="mae" name="MAE (min)" stroke={C.violet} strokeWidth={2.5} dot={false} /></LineChart></ResponsiveContainer>
          ) : <Empty title="No data yet" />}</div>
        </Card>

        <Card className="lg:col-span-2">
          <CardTitle sub="1-hour horizon forecasts scored once the hour has passed">Demand forecast accuracy</CardTitle>
          {m.demand.n ? <div className="grid gap-3 sm:grid-cols-3"><Metric label="WAPE" value={pct(m.demand.wape)} hint="lower is better" /><Metric label="MAE" value={m.demand.mae} unit="arrivals" /><Metric label="Scored forecasts" value={m.demand.n} /></div>
            : <p className="text-sm text-muted">Forecasts are stored as the dashboard runs and scored automatically after their hour ends.</p>}
        </Card>
      </div>
    </>
  )
}
