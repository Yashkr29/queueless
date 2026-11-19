import { useState } from 'react'
import { Lightbulb, Plus } from 'lucide-react'
import { api, errorMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { applyAction } from '../../lib/actions'
import { useLiveEvent, usePoll } from '../../lib/live'
import { Badge, Button, Card, CardTitle, ErrorBox, Field, Input, PageHeader, Select, Spinner, useToast } from '../../components/ui'

const STATUS_TONE = { open: 'green', closed: 'slate', unavailable: 'amber' }

export default function Counters() {
  const { user } = useAuth()
  const admin = user.role === 'admin'
  const toast = useToast()
  const counters = usePoll(() => api.get('/admin/counters').then((r) => r.data), [], 15000)
  const staff = usePoll(() => api.get('/admin/staff').then((r) => r.data), [], 30000)
  const services = usePoll(() => api.get('/services').then((r) => r.data), [])
  const perf = usePoll(() => api.get('/analytics/counter-performance?days=14').then((r) => r.data), [], 60000)
  const recs = usePoll(() => api.get('/admin/recommendations').then((r) => r.data), [], 30000)
  const [err, setErr] = useState('')
  const [newC, setNewC] = useState('')
  const [newS, setNewS] = useState({ name: '', email: '', password: '' })
  const reloadAll = () => { counters.reload(); staff.reload(); recs.reload(); perf.reload() }
  useLiveEvent((m) => { if (m.type === 'queue_changed') counters.reload() })

  const guard = async (fn, ok) => { setErr(''); try { await fn(); if (ok) toast(ok); reloadAll() } catch (e) { setErr(errorMessage(e)) } }
  const patch = (c, body, ok) => guard(() => api.patch(`/admin/counters/${c.counter_id}`, body), ok)
  const perfOf = (id) => perf.data?.find((p) => p.counter_id === id)
  const svcName = (id) => services.data?.find((s) => s.service.service_id === id)?.service.service_name || `#${id}`

  if (counters.loading) return <Spinner />
  return (
    <>
      <PageHeader title="Counters & staff" sub={admin ? 'Open, close and configure counters. Every change is audited.' : 'Read-only view — administrators can change configuration.'} />
      {err && <div className="mb-4"><ErrorBox>{err}</ErrorBox></div>}

      {recs.data?.recommendations.length > 0 && (
        <Card className="mb-5 !bg-gradient-to-br !from-brand-50 !to-white">
          <CardTitle sub={recs.data.note} right={<Badge tone="blue">Rule-based · greedy</Badge>}>Recommendations</CardTitle>
          <ul className="space-y-3">
            {recs.data.recommendations.map((r, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white p-4 ring-1 ring-line">
                <div className="flex items-start gap-3"><Lightbulb className="mt-0.5 h-5 w-5 text-amber-500" aria-hidden /><div><p className="font-medium">{r.title}</p><p className="text-sm text-muted">{r.rationale}</p></div></div>
                {r.action && admin && <Button size="sm" onClick={() => guard(() => applyAction(r.action), 'Applied')}>{r.action.label}</Button>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {counters.data.map((c) => {
          const p = perfOf(c.counter_id)
          return (
            <Card key={c.counter_id}>
              <div className="flex items-start justify-between"><div><h3 className="text-base font-semibold">{c.counter_name}</h3><p className="text-xs text-muted">{c.busy ? `Serving ${c.current_token}` : 'Idle'} · {c.served_today} served today</p></div><Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge></div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-xl bg-surface p-2"><p className="text-muted">Utilization</p><p className="mt-0.5 text-base font-semibold">{p ? Math.round(p.utilization * 100) : 0}%</p></div>
                <div className="rounded-xl bg-surface p-2"><p className="text-muted">Avg service</p><p className="mt-0.5 text-base font-semibold">{p?.avg_service_minutes != null ? `${Math.round(p.avg_service_minutes)}m` : '—'}</p></div>
                <div className="rounded-xl bg-surface p-2"><p className="text-muted">Served (14d)</p><p className="mt-0.5 text-base font-semibold">{p?.served ?? 0}</p></div>
              </div>
              <div className="mt-4 space-y-3">
                <Field label="Status"><Select disabled={!admin} value={c.status} onChange={(e) => patch(c, { status: e.target.value }, `${c.counter_name} ${e.target.value}`)}><option value="open">Open</option><option value="closed">Closed</option><option value="unavailable">Unavailable</option></Select></Field>
                <Field label="Assigned staff"><Select disabled={!admin} value={c.assigned_staff_id ?? ''} onChange={(e) => patch(c, e.target.value ? { assigned_staff_id: Number(e.target.value) } : { unassign_staff: true }, 'Staff updated')}>
                  <option value="">Unassigned</option>{staff.data?.map((s) => <option key={s.staff_id} value={s.staff_id}>{s.name}{s.assigned_counter_id && s.assigned_counter_id !== c.counter_id ? ` (at ${s.assigned_counter})` : ''}</option>)}</Select></Field>
                <fieldset><legend className="mb-1.5 text-xs font-medium text-slate-600">Supported services</legend>
                  <div className="flex flex-wrap gap-1.5">
                    {services.data?.map((s) => {
                      const id = s.service.service_id, on = c.service_ids.includes(id)
                      return <button key={id} type="button" disabled={!admin} aria-pressed={on} onClick={() => patch(c, { service_ids: on ? c.service_ids.filter((x) => x !== id) : [...c.service_ids, id] })}
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${on ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>{s.service.service_name}</button>
                    })}
                  </div></fieldset>
              </div>
            </Card>
          )
        })}
        {admin && (
          <Card className="border-2 border-dashed !bg-transparent !shadow-none">
            <CardTitle>Add a counter</CardTitle>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); guard(async () => { await api.post('/admin/counters', { counter_name: newC, service_ids: services.data.map((s) => s.service.service_id) }); setNewC('') }, 'Counter created') }}>
              <Input required placeholder="e.g. Counter 6" value={newC} onChange={(e) => setNewC(e.target.value)} aria-label="Counter name" /><Button type="submit"><Plus className="h-4 w-4" aria-hidden />Add</Button>
            </form>
            <p className="mt-2 text-xs text-muted">New counters start closed and support all services; adjust after creating.</p>
          </Card>
        )}
      </div>

      <Card className="mt-5">
        <CardTitle sub="Availability affects wait estimates immediately">Staff</CardTitle>
        <div className="overflow-x-auto"><table className="w-full min-w-[520px] text-left text-sm">
          <thead className="text-xs text-muted"><tr><th className="py-2 font-medium">Name</th><th className="py-2 font-medium">Email</th><th className="py-2 font-medium">Counter</th><th className="py-2 font-medium">Availability</th></tr></thead>
          <tbody className="divide-y divide-line">{staff.data?.map((s) => (
            <tr key={s.staff_id}><td className="py-3 font-medium">{s.name}</td><td className="py-3 text-muted">{s.email}</td><td className="py-3">{s.assigned_counter || <span className="text-muted">—</span>}</td>
              <td className="py-3"><Select className="!w-36 !py-1.5" disabled={!admin} value={s.availability} onChange={(e) => guard(() => api.patch(`/admin/staff/${s.staff_id}`, { availability: e.target.value }), 'Availability updated')}><option value="available">Available</option><option value="busy">Busy</option><option value="off">Off duty</option></Select></td></tr>
          ))}</tbody></table></div>
        {admin && (
          <form className="mt-4 grid gap-2 border-t border-line pt-4 sm:grid-cols-[1fr_1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); guard(async () => { await api.post('/admin/staff', newS); setNewS({ name: '', email: '', password: '' }) }, 'Staff account created') }}>
            <Input required placeholder="Full name" value={newS.name} onChange={(e) => setNewS({ ...newS, name: e.target.value })} aria-label="Staff name" />
            <Input required type="email" placeholder="Email" value={newS.email} onChange={(e) => setNewS({ ...newS, email: e.target.value })} aria-label="Staff email" />
            <Input required type="password" minLength={8} placeholder="Temporary password" value={newS.password} onChange={(e) => setNewS({ ...newS, password: e.target.value })} aria-label="Temporary password" />
            <Button type="submit"><Plus className="h-4 w-4" aria-hidden />Add staff</Button>
          </form>
        )}
      </Card>
    </>
  )
}
