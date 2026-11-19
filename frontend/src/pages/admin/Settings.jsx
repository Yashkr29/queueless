import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { usePoll } from '../../lib/live'
import { dateTime } from '../../lib/format'
import { Button, Card, CardTitle, ErrorBox, Field, Input, PageHeader, Spinner, useToast } from '../../components/ui'

const LABELS = {
  congestion_queue_length: ['Congestion queue length', 'Alert when more than this many customers are waiting for a service.'],
  wait_threshold_minutes: ['Wait threshold (min)', 'Recommend another counter when a new customer would wait longer than this.'],
  rapid_growth_delta: ['Rapid growth (customers / 15 min)', 'Alert when the queue grows by this much in 15 minutes.'],
  approaching_ahead: ['“Approaching turn” at', 'Notify customers when this many or fewer are ahead.'],
  arrival_buffer_minutes: ['Arrival safety buffer (min)', 'How early before the predicted service time customers are advised to arrive.'],
  delay_notify_minutes: ['Delay notice (min)', 'Tell the customer when their estimate slips by this much.'],
  rejoin_cooldown_minutes: ['No-show rejoin cooldown (min)', 'How long a customer who missed their turn waits before rejoining the same service.'],
  capacity_alert_ratio: ['Demand / capacity alert ratio', 'Alert when predicted workload exceeds this multiple of capacity.'],
  target_utilization: ['Target utilization (0–1)', 'Counter allocation aims to keep load below this fraction of capacity.'],
}

export default function Settings() {
  const { user } = useAuth()
  const admin = user.role === 'admin'
  const toast = useToast()
  const s = usePoll(() => api.get('/admin/settings').then((r) => r.data), [])
  const audit = usePoll(() => (admin ? api.get('/admin/audit?page_size=30').then((r) => r.data) : Promise.resolve(null)), [admin])
  const [vals, setVals] = useState({})
  const [err, setErr] = useState('')
  useEffect(() => { if (s.data) setVals(s.data.settings) }, [s.data])

  const save = async (e) => {
    e.preventDefault(); setErr('')
    const body = Object.fromEntries(Object.keys(LABELS).map((k) => [k, Number(vals[k])]))
    try { await api.patch('/admin/settings', { values: body }); toast('Settings saved'); s.reload(); audit.reload() } catch (x) { setErr(errorMessage(x)) }
  }
  if (s.loading) return <Spinner />
  return (
    <>
      <PageHeader title="Settings" sub="Thresholds used by the alert and recommendation engine." />
      <div className="grid gap-5 xl:grid-cols-[1fr_1.1fr]">
        <Card>
          <CardTitle>Operational thresholds</CardTitle>
          <form onSubmit={save} className="space-y-4">
            {err && <ErrorBox>{err}</ErrorBox>}
            {Object.entries(LABELS).map(([k, [label, hint]]) => (
              <Field key={k} label={label} hint={hint}><Input type="number" step="any" min="0" disabled={!admin} value={vals[k] ?? ''} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} /></Field>
            ))}
            {admin ? <Button type="submit">Save settings</Button> : <p className="text-sm text-muted">Only administrators can change settings.</p>}
          </form>
        </Card>
        {admin && (
          <Card className="!p-0 overflow-hidden">
            <div className="px-5 pt-5"><CardTitle sub="Overrides and configuration changes, newest first">Audit log</CardTitle></div>
            <div className="max-h-[640px] overflow-auto"><table className="w-full min-w-[480px] text-left text-sm"><thead className="sticky top-0 bg-surface text-xs text-muted"><tr><th className="px-5 py-3 font-medium">When</th><th className="px-5 py-3 font-medium">Who</th><th className="px-5 py-3 font-medium">Action</th></tr></thead>
              <tbody className="divide-y divide-line">{audit.data?.items.map((a) => (
                <tr key={a.audit_id}><td className="whitespace-nowrap px-5 py-3 text-muted">{dateTime(a.created_at)}</td><td className="px-5 py-3">{a.actor || '—'}</td>
                  <td className="px-5 py-3"><span className="font-medium">{a.action.replaceAll('_', ' ')}</span>{a.details?.reason && <span className="block text-xs text-muted">“{a.details.reason}”</span>}</td></tr>))}
                {!audit.data?.items.length && <tr><td colSpan="3" className="px-5 py-8 text-center text-muted">No audited actions yet.</td></tr>}</tbody></table></div>
          </Card>
        )}
      </div>
    </>
  )
}
