import { useState } from 'react'
import { Download, FileText } from 'lucide-react'
import { api, download, errorMessage } from '../../lib/api'
import { usePoll } from '../../lib/live'
import { mins, pct } from '../../lib/format'
import { Badge, Button, Card, CardTitle, ErrorBox, Input, PageHeader, Spinner } from '../../components/ui'

const today = () => new Date().toISOString().slice(0, 10)

export default function Reports() {
  const [day, setDay] = useState(today())
  const [err, setErr] = useState('')
  const { data: r, loading } = usePoll(() => api.get(`/analytics/reports/daily?day=${day}`).then((x) => x.data), [day])
  const get = async (fmt) => { setErr(''); try { await download(`/analytics/reports/daily?day=${day}&format=${fmt}`, `queueless-report-${day}.${fmt}`) } catch (e) { setErr(errorMessage(e)) } }

  return (
    <>
      <PageHeader title="Daily report" sub="Operational summary with export." actions={<>
        <Input type="date" value={day} max={today()} onChange={(e) => e.target.value && setDay(e.target.value)} className="!w-auto" aria-label="Report date" />
        <Button variant="ghost" onClick={() => get('csv')}><Download className="h-4 w-4" aria-hidden />CSV</Button>
        <Button onClick={() => get('pdf')}><FileText className="h-4 w-4" aria-hidden />PDF</Button></>} />
      {err && <div className="mb-4"><ErrorBox>{err}</ErrorBox></div>}
      {loading ? <Spinner /> : r && (
        <div className="space-y-5">
          <div className="flex items-center gap-2 text-sm text-muted"><Badge tone={r.data_note === 'Live data' ? 'green' : 'amber'}>{r.data_note}</Badge>{r.date}</div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {[['Total tokens', r.total_tokens], ['Customers served', r.customers_served], ['Avg wait', mins(r.avg_wait_minutes)], ['Avg service', mins(r.avg_service_minutes)], ['Abandonment', pct(r.abandonment_rate)]].map(([k, v]) => (
              <Card key={k} className="!p-4"><p className="text-xs text-muted">{k}</p><p className="mt-1 text-2xl font-semibold">{v}</p></Card>))}
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card><CardTitle>Peak traffic periods</CardTitle>{r.peak_periods.length ? <ul className="space-y-2">{r.peak_periods.map((p) => <li key={p.hour} className="flex justify-between rounded-xl bg-surface px-4 py-2.5 text-sm"><span>{String(p.hour).padStart(2, '0')}:00</span><b>{p.arrivals} arrivals</b></li>)}</ul> : <p className="text-sm text-muted">No arrivals on this day.</p>}</Card>
            <Card><CardTitle sub={r.prediction_mae_minutes != null ? `${r.prediction_samples} predictions scored` : 'No scored predictions for this day'}>Prediction accuracy</CardTitle><p className="text-3xl font-semibold">{r.prediction_mae_minutes != null ? `${r.prediction_mae_minutes} min` : '—'}<span className="ml-2 text-sm font-normal text-muted">mean absolute error</span></p></Card>
          </div>
          <Card className="!p-0 overflow-hidden"><div className="px-5 pt-5"><CardTitle>Counter utilization</CardTitle></div>
            <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm"><thead className="bg-surface text-xs text-muted"><tr>{['Counter', 'Served', 'Avg service', 'Avg wait', 'Utilization'].map((h) => <th key={h} className="px-5 py-3 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">{r.counter_utilization.map((c) => <tr key={c.counter_id}><td className="px-5 py-3 font-medium">{c.counter_name}</td><td className="px-5 py-3">{c.served}</td><td className="px-5 py-3">{mins(c.avg_service_minutes)}</td><td className="px-5 py-3">{mins(c.avg_wait_minutes)}</td><td className="px-5 py-3">{pct(c.utilization)}</td></tr>)}</tbody></table></div></Card>
          <Card><CardTitle>Operational recommendations</CardTitle><ul className="list-inside list-disc space-y-1.5 text-sm text-slate-700">{r.recommendations.map((x, i) => <li key={i}>{x}</li>)}</ul></Card>
        </div>
      )}
    </>
  )
}
