import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../../lib/api'
import { usePoll } from '../../lib/live'
import { orgType, useLocations } from '../../lib/location'
import { PRIORITIES, mins } from '../../lib/format'
import { Button, Card, EstimateBadge, ErrorBox, Modal, PageHeader, Spinner, useToast } from '../../components/ui'

export default function Join() {
  const services = usePoll(() => api.get('/services').then((r) => r.data), [], 20000)
  const mine = usePoll(() => api.get('/queue/mine?active_only=true').then((r) => r.data), [], 30000)
  const { locations, current, setCurrent } = useLocations()
  const [pick, setPick] = useState(null)
  const [priority, setPriority] = useState('none')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const navigate = useNavigate()
  const toast = useToast()
  const activeFor = (sid) => mine.data?.find((t) => t.service.service_id === sid)

  const join = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.post('/queue/join', { service_id: pick.service.service_id, priority_type: priority })
      toast(`Token ${r.data.token_label} issued`)
      navigate(`/app/token/${r.data.token_id}`)
    } catch (e) { setErr(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHeader title="Join a queue" sub="Pick a service. Come back at your recommended time." />
      {locations.length > 1 && (
        <div className="mb-5" role="group" aria-label="Choose where you are going">
          <p className="mb-2 text-[13px] font-semibold text-muted">Where are you going?</p>
          <div className="flex flex-wrap gap-2">
            {locations.map((l) => { const Icon = orgType(l.location_type).icon; const on = l.location_id === current; return (
              <button key={l.location_id} type="button" aria-pressed={on} onClick={() => setCurrent(l.location_id)} className={`inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold ${on ? 'bg-brand-600 text-brand-50' : 'border border-brand-200 bg-white text-brand-600 hover:bg-brand-50'}`}><Icon className="h-4 w-4" aria-hidden />{l.name}</button>) })}
          </div>
        </div>
      )}
      {services.loading ? <Spinner /> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {services.data.map((s) => {
            const have = activeFor(s.service.service_id)
            const e = s.estimate
            return (
              <Card key={s.service.service_id} className="flex flex-col gap-3 !p-4 !rounded-3xl">
                <div className="flex items-center gap-3">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-[14px] bg-brand-100 font-display text-lg font-semibold text-brand-600">{s.service.code}</span>
                  <div className="min-w-0 flex-1"><h3 className="text-base font-semibold">{s.service.service_name}</h3><p className="truncate text-xs text-muted">{s.service.description}</p></div>
                </div>
                <dl className="grid grid-cols-3 gap-2 text-center">
                  <div className="rounded-[14px] bg-slate-50 px-1 py-2"><dt className="text-[11px] text-muted">Waiting</dt><dd className="font-display text-xl font-semibold">{s.queue_length}</dd></div>
                  <div className="rounded-[14px] bg-slate-50 px-1 py-2"><dt className="text-[11px] text-muted">Counters</dt><dd className="font-display text-xl font-semibold">{s.active_counters}</dd></div>
                  <div className="rounded-[14px] bg-brand-600 px-1 py-2 text-brand-50"><dt className="text-[11px] text-brand-200">Est. wait</dt><dd className="font-display text-xl font-semibold">{e.wait_minutes != null ? mins(e.wait_minutes) : '—'}</dd></div>
                </dl>
                <div className="flex items-center justify-between gap-2"><span className="text-xs text-muted">{e.lower_minutes != null ? `Expected range ${Math.round(e.lower_minutes)}–${Math.round(e.upper_minutes)} min` : e.method === 'unavailable' ? 'No counter is open right now.' : 'No confidence range for this estimate.'}</span><EstimateBadge estimate={e} /></div>
                {have ? <Link to={`/app/token/${have.token_id}`} className="inline-flex min-h-11 items-center justify-center rounded-full bg-brand-100 px-5 text-sm font-semibold text-brand-600 hover:bg-brand-200/60">View {have.token_label}</Link>
                  : <Button onClick={() => { setPick(s); setPriority('none'); setErr('') }}>Join queue</Button>}
              </Card>
            )
          })}
        </div>
      )}
      {!services.loading && !services.data?.length && <Card><p className="text-sm text-muted">No services are available right now.</p></Card>}

      <Modal open={!!pick} onClose={() => setPick(null)} title={pick ? `Join ${pick.service.service_name}` : ''}>
        {pick && (
          <div className="space-y-4">
            {err && <ErrorBox>{err}</ErrorBox>}
            <p className="text-sm leading-relaxed text-muted">Current estimate about <strong className="text-ink">{pick.estimate.wait_minutes != null ? mins(pick.estimate.wait_minutes) : 'not available yet'}</strong>{pick.estimate.lower_minutes != null && ` (range ${Math.round(pick.estimate.lower_minutes)}–${Math.round(pick.estimate.upper_minutes)})`}. It updates as the queue moves.</p>
            <fieldset className="space-y-2">
              <legend className="pb-2 text-[13px] font-semibold">Priority category</legend>
              {PRIORITIES.map((p) => (
                <label key={p.value} className={`flex min-h-[52px] cursor-pointer items-center gap-3 rounded-[18px] border-2 px-4 text-[15px] font-medium ${priority === p.value ? 'border-brand-600 bg-brand-50' : 'border-line bg-white'}`}>
                  <input type="radio" name="priority" checked={priority === p.value} onChange={() => setPriority(p.value)} className="h-5 w-5 accent-[#124559]" />{p.label}
                </label>
              ))}
            </fieldset>
            <p className="text-xs leading-relaxed text-muted">Senior, disability and pregnancy priority is verified at the counter. Emergencies are handled by staff.</p>
            <div className="grid grid-cols-[1fr_1.6fr] gap-2.5"><Button variant="ghost" className="min-h-[54px]" onClick={() => setPick(null)}>Cancel</Button><Button className="min-h-[54px]" onClick={join} loading={busy}>Confirm and get token</Button></div>
          </div>
        )}
      </Modal>
    </>
  )
}
