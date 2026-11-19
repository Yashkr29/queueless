import { useEffect, useState } from 'react'
import { ListChecks, PhoneCall, Play, CheckCheck, UserX, ChevronsRight } from 'lucide-react'
import { api, errorMessage } from '../../lib/api'
import { useDebounced, useLiveEvent, usePoll } from '../../lib/live'
import { dateTime, mins, time } from '../../lib/format'
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, Select, Spinner, StatusBadge, useToast } from '../../components/ui'

const PRIO = { none: null, senior: 'Senior', disabled: 'Disability', pregnant: 'Pregnant', emergency: 'Emergency' }
const WAITING = ['booked', 'confirmed', 'waiting', 'approaching']
const EVENT_LABEL = {
  token_created: 'Token created', confirmed_on_my_way: 'Customer is on the way', arrived: 'Checked in at the centre', approaching: 'Approaching: few customers ahead',
  called: 'Called to a counter', service_started: 'Service started', service_completed: 'Service completed', cancelled: 'Cancelled', no_show: 'Marked no-show',
  priority_changed: 'Priority changed', delay_notified: 'Customer told about a delay', expired: 'Expired at end of day',
}
const FILTERS = [['all', 'All'], ['waiting', 'Waiting'], ['called', 'Called'], ['serving', 'Serving']]

export default function LiveQueue() {
  const [service, setService] = useState('')
  const [filter, setFilter] = useState('all')
  const [selId, setSelId] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const toast = useToast()
  const q = usePoll(() => api.get(`/admin/queue?page_size=200${service ? `&service_id=${service}` : ''}`).then((r) => r.data), [service], 10000)
  const counters = usePoll(() => api.get('/admin/counters').then((r) => r.data), [], 10000)
  const services = usePoll(() => api.get('/services').then((r) => r.data), [])
  const refresh = () => { q.reload(); counters.reload(); events.reload() }
  const refreshLive = useDebounced(() => refresh())
  useLiveEvent((m) => { if (m.type === 'queue_changed') refreshLive() })

  const all = q.data?.items || []
  const counts = { all: all.length, waiting: all.filter((t) => WAITING.includes(t.status)).length, called: all.filter((t) => t.status === 'called').length, serving: all.filter((t) => t.status === 'serving').length }
  const items = all.filter((t) => filter === 'all' || (filter === 'waiting' ? WAITING.includes(t.status) : t.status === filter))
  const sel = all.find((t) => t.token_id === selId) || items[0] || null
  const events = usePoll(() => (sel ? api.get(`/admin/queue/${sel.token_id}/events`).then((r) => r.data) : Promise.resolve(null)), [sel?.token_id, sel?.status], 0)
  useEffect(() => { if (selId && !all.find((t) => t.token_id === selId)) setSelId(null) }, [q.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (key, fn, ok) => {
    setBusy(key); setErr('')
    try { await fn(); toast(ok); refresh() }
    catch (e) {
      const msg = errorMessage(e)
      if (e.response?.status === 409 && /override reason/i.test(msg)) {   // fairness guard: out-of-order calls need a recorded reason
        const reason = window.prompt(`${msg}\n\nReason for calling out of order (will be audited):`)
        if (reason?.trim()) return run(key, () => fn(reason.trim()), ok)
      } else setErr(msg)
    } finally { setBusy('') }
  }
  const idleFor = (t) => counters.data?.filter((c) => c.status === 'open' && !c.busy && c.service_ids.includes(t.service_id)) || []
  const call = (t, counterId) => run(`c${t.token_id}`, (reason) => api.post(`/admin/queue/${t.token_id}/call`, { counter_id: counterId || null, override_reason: reason || null }), `Called ${t.token_label}`)
  const post = (t, action, ok, body) => run(`${action}${t.token_id}`, () => api.post(`/admin/queue/${t.token_id}/${action}`, body), ok)
  const changePriority = (t) => {
    const v = window.prompt('New priority: none, senior, disabled, pregnant or emergency', t.priority_type)
    if (!v) return
    const reason = window.prompt('Reason (will be audited):')
    if (reason?.trim()) run(`p${t.token_id}`, () => api.patch(`/admin/queue/${t.token_id}`, { priority_type: v.trim().toLowerCase(), reason: reason.trim() }), 'Priority updated')
  }

  return (
    <>
      <PageHeader eyebrow="Live · updates instantly" title="Live queue" actions={
        <Select value={service} onChange={(e) => setService(e.target.value)} aria-label="Filter by service" className="!w-auto !rounded-full"><option value="">All services</option>{services.data?.map((s) => <option key={s.service.service_id} value={s.service.service_id}>{s.service.service_name}</option>)}</Select>} />
      {err && <div className="mb-4"><ErrorBox>{err}</ErrorBox></div>}

      <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {counters.data?.map((c) => {
          const dark = c.busy
          const closed = c.status !== 'open'
          return (
            <section key={c.counter_id} className={`flex flex-col gap-3 rounded-3xl border p-[18px] ${dark ? 'border-brand-600 bg-brand-600 text-brand-50' : closed ? 'border-[#cfdcc6] bg-[#e1ebd2]' : 'border-line bg-white'}`}>
              <div className="flex items-center justify-between gap-2"><span className="font-display text-lg font-semibold">{c.counter_name}</span>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${dark ? 'bg-brand-50 text-brand-600' : closed ? 'bg-white text-muted' : 'bg-brand-100 text-brand-600'}`}>{dark ? 'Serving' : closed ? c.status : 'Idle'}</span></div>
              <p className={`text-[13px] ${dark ? 'text-brand-200' : 'text-muted'}`}>{c.staff_name || 'No staff assigned'}</p>
              <div><p className="font-display text-[26px] font-semibold leading-tight">{c.busy ? c.current_token : closed ? '—' : 'Free'}</p><p className={`text-xs ${dark ? 'text-brand-200' : 'text-muted'}`}>{c.busy ? 'in progress' : closed ? 'not open' : 'ready for next'}</p></div>
              <Button size="sm" variant={dark ? 'soft' : 'primary'} className={dark ? '!bg-brand-50/15 !text-brand-50' : ''} disabled={closed || c.busy} loading={busy === `n${c.counter_id}`}
                onClick={() => run(`n${c.counter_id}`, () => api.post('/admin/queue/call-next', { counter_id: c.counter_id }), `Called next for ${c.counter_name}`)}><ChevronsRight className="h-4 w-4" aria-hidden />Call next</Button>
            </section>
          )
        })}
      </div>

      <div className="flex flex-wrap items-start gap-5">
        <Card className="min-w-0 flex-[999_1_640px] overflow-hidden !p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 px-6 pb-4 pt-6">
            <h3 className="font-display text-xl font-semibold tracking-tight">Active tokens</h3>
            <div role="group" aria-label="Status filter" className="flex flex-wrap gap-2">
              {FILTERS.map(([k, l]) => <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)} className={`min-h-10 rounded-full px-4 text-[13px] font-semibold ${filter === k ? 'bg-brand-600 text-brand-50' : 'border border-brand-200 bg-white text-brand-600 hover:bg-brand-50'}`}>{l} · {counts[k]}</button>)}
            </div>
          </div>
          {q.loading ? <Spinner /> : !items.length ? <Empty icon={ListChecks} title="The queue is empty">New tokens appear here instantly.</Empty> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="bg-slate-50 text-xs text-muted"><tr>{['Token', 'Customer', 'Status', 'Pos.', 'Waited', 'Est. wait', 'Action'].map((h, i) => <th key={h} scope="col" className={`py-3 font-semibold ${i === 0 ? 'pl-6 pr-2' : i === 6 ? 'pl-2 pr-6 text-right' : 'px-2'}`}>{h}</th>)}</tr></thead>
                <tbody>
                  {items.map((t) => {
                    const pr = PRIO[t.priority_type]
                    const waiting = WAITING.includes(t.status)
                    const idle = idleFor(t)
                    const on = sel?.token_id === t.token_id
                    return (
                      <tr key={t.token_id} onClick={() => setSelId(t.token_id)} className={`cursor-pointer border-t border-line ${on ? 'bg-[#f1f7e6]' : 'hover:bg-slate-50/70'}`}>
                        <td className="py-3.5 pl-6 pr-2"><span className="flex items-center gap-2.5"><span className="font-display text-lg font-semibold">{t.token_label}</span>{pr && <Badge tone="blue">{pr}</Badge>}</span><span className="mt-0.5 block text-xs text-muted">{t.service_name}</span></td>
                        <td className="px-2 py-3.5 font-medium">{t.customer_name}{t.arrived && <span className="block text-xs text-brand-600">Checked in</span>}</td>
                        <td className="px-2 py-3.5"><StatusBadge status={t.status} /></td>
                        <td className="px-2 py-3.5 font-semibold">{t.queue_position ?? '—'}</td>
                        <td className="px-2 py-3.5">{mins(t.waited_minutes)}</td>
                        <td className="px-2 py-3.5"><span className="font-semibold">{t.estimate?.wait_minutes != null ? mins(t.estimate.wait_minutes) : t.counter_name || '—'}</span>{t.estimate?.lower_minutes != null && <span className="block text-xs text-muted">range {Math.round(t.estimate.lower_minutes)}–{Math.round(t.estimate.upper_minutes)}</span>}</td>
                        <td className="py-3.5 pl-2 pr-6 text-right" onClick={(e) => e.stopPropagation()}>
                          {waiting && <Button size="sm" variant="ghost" disabled={!idle.length} title={idle.length ? '' : 'No idle counter supports this service'} loading={busy === `c${t.token_id}`} onClick={() => call(t, idle[0]?.counter_id)}>Call</Button>}
                          {t.status === 'called' && <Button size="sm" loading={busy === `start${t.token_id}`} onClick={() => post(t, 'start', 'Service started')}>Start</Button>}
                          {t.status === 'serving' && <Button size="sm" loading={busy === `complete${t.token_id}`} onClick={() => post(t, 'complete', 'Service completed')}>Complete</Button>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="border-t border-line px-6 py-4 text-[13px] leading-relaxed text-muted">Order is priority first, then joining time. Calling someone out of order needs a reason and is written to the audit log. AI estimates never change the order.</p>
        </Card>

        {sel && (
          <aside aria-label="Selected token" className="flex min-w-0 max-w-[460px] flex-[1_1_340px] flex-col gap-[18px] rounded-[28px] border border-line bg-white p-6">
            <div className="flex items-start justify-between gap-3">
              <div><p className="text-xs font-semibold uppercase tracking-[0.1em] text-muted">Selected</p><p className="font-display text-[44px] font-semibold leading-[1.05] tracking-tight">{sel.token_label}</p><p className="mt-0.5 text-sm text-muted">{sel.customer_name} · {sel.service_name}</p></div>
              <StatusBadge status={sel.status} />
            </div>
            <div className="grid grid-cols-3 gap-2.5">
              {[['Position', sel.queue_position ?? '—'], ['Counter', sel.counter_name || '—'], ['Waited', mins(sel.waited_minutes)]].map(([k, v]) => (
                <div key={k} className="rounded-2xl bg-slate-50 p-3"><p className="text-xs text-muted">{k}</p><p className="mt-0.5 truncate font-display text-xl font-semibold">{v}</p></div>
              ))}
            </div>
            {sel.estimate && (
              <div className="rounded-[20px] bg-brand-600 p-4 text-brand-50">
                <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold uppercase tracking-[0.08em] text-brand-200">{sel.estimate.method === 'ml' ? 'AI estimate' : 'Estimate'}</span>{sel.estimate.trained_on === 'synthetic' && <span className="rounded-full bg-brand-50/15 px-2.5 py-1 text-[11px]">simulated training data</span>}</div>
                <p className="mt-2 font-display text-[34px] font-semibold leading-tight">{sel.estimate.wait_minutes != null ? mins(sel.estimate.wait_minutes) : '—'}{sel.estimate.lower_minutes != null && <span className="ml-2 text-[15px] font-medium text-brand-200">range {Math.round(sel.estimate.lower_minutes)}–{Math.round(sel.estimate.upper_minutes)}</span>}</p>
                <p className="mt-1.5 text-[13px] leading-relaxed text-brand-200">{sel.estimate.note}</p>
              </div>
            )}
            <div>
              <h4 className="mb-3 text-sm font-semibold">Timeline</h4>
              {events.data?.events?.length ? (
                <ol className="space-y-3.5">
                  {events.data.events.map((e) => (
                    <li key={e.event_id} className="grid grid-cols-[14px_1fr_auto] items-start gap-3"><span className="mt-1.5 h-2.5 w-2.5 rounded-full bg-brand-600 shadow-[0_0_0_4px_rgba(18,69,89,0.15)]" /><span className="text-sm font-medium">{EVENT_LABEL[e.event_type] || e.event_type.replaceAll('_', ' ')}</span><span className="text-[13px] text-muted" title={dateTime(e.timestamp)}>{time(e.timestamp)}</span></li>
                  ))}
                </ol>
              ) : <p className="text-sm text-muted">No events yet.</p>}
            </div>
            <div className="flex flex-col gap-2.5">
              {WAITING.includes(sel.status) && <Button disabled={!idleFor(sel).length} loading={busy === `c${sel.token_id}`} onClick={() => call(sel, idleFor(sel)[0]?.counter_id)}><PhoneCall className="h-4 w-4" aria-hidden />{idleFor(sel).length ? `Call to ${idleFor(sel)[0].counter_name}` : 'No idle counter'}</Button>}
              {sel.status === 'called' && <div className="grid grid-cols-2 gap-2.5"><Button loading={busy === `start${sel.token_id}`} onClick={() => post(sel, 'start', 'Service started')}><Play className="h-4 w-4" aria-hidden />Start</Button><Button variant="danger" onClick={() => confirm('Mark as no-show?') && post(sel, 'no-show', 'Marked no-show')}><UserX className="h-4 w-4" aria-hidden />No-show</Button></div>}
              {sel.status === 'serving' && <Button loading={busy === `complete${sel.token_id}`} onClick={() => post(sel, 'complete', 'Service completed')}><CheckCheck className="h-4 w-4" aria-hidden />Complete</Button>}
              {sel.status !== 'serving' && (
                <div className="grid grid-cols-2 gap-2.5">
                  <Button variant="ghost" disabled={!WAITING.includes(sel.status)} onClick={() => changePriority(sel)}>Change priority</Button>
                  <Button variant="danger" onClick={() => { const reason = window.prompt('Reason for cancelling (optional):'); if (reason !== null) post(sel, 'cancel', 'Token cancelled', { reason: reason || null }) }}>Cancel token</Button>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
    </>
  )
}
