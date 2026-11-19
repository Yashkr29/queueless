import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Check, Clock, Footprints, MapPin } from 'lucide-react'
import { api, errorMessage } from '../../lib/api'
import { useLiveEvent, usePoll } from '../../lib/live'
import { time } from '../../lib/format'
import { useLocations } from '../../lib/location'
import { Button, Card, ErrorBox, EstimateBadge, RangeBar, Spinner, StatusBadge, useToast } from '../../components/ui'

const STEPS = [['booked', 'Booked'], ['waiting', 'Waiting'], ['approaching', 'Near'], ['called', 'Called'], ['serving', 'Serving'], ['completed', 'Done']]
const stepIndex = (s) => ({ booked: 0, confirmed: 0, waiting: 1, approaching: 2, called: 3, serving: 4, completed: 5 }[s] ?? -1)

function Stepper({ status }) {
  const i = stepIndex(status)
  return (
    <ol className="grid grid-cols-6" aria-label={`Progress: step ${i + 1} of 6`}>
      {STEPS.map(([k, label], n) => (
        <li key={k} className="relative flex flex-col items-center gap-2" aria-current={n === i ? 'step' : undefined}>
          {n > 0 && <span className={`absolute right-1/2 top-[10px] h-[3px] w-full ${n <= i ? 'bg-brand-200' : 'bg-brand-50/20'}`} />}
          <span className={`relative z-10 grid h-[22px] w-[22px] place-items-center rounded-full text-brand-600 ${n < i ? 'bg-brand-200' : n === i ? 'bg-brand-50 shadow-[0_0_0_5px_rgba(239,246,224,0.25)]' : 'bg-brand-50/20'}`}>{n < i && <Check className="h-3 w-3" strokeWidth={3.5} aria-hidden />}</span>
          <span className={`text-[11px] font-medium ${n <= i ? 'text-brand-50' : 'text-brand-200'}`}>{label}</span>
        </li>
      ))}
    </ol>
  )
}

export default function Token() {
  const { id } = useParams()
  const toast = useToast()
  const { nameOf } = useLocations()
  const { data, error, loading, reload } = usePoll(() => api.get(`/queue/${id}`).then((r) => r.data), [id], 20000)
  const [live, setLive] = useState(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [, tick] = useState(0)
  useEffect(() => { setLive(null) }, [data])
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 30000); return () => clearInterval(t) }, [])
  useLiveEvent((m) => {
    if (m.type !== 'token_update' || String(m.token.token_id) !== String(id)) return
    if (m.token.service) setLive(m.token); else reload()
  })
  const t = live || data

  const act = async (key, path, msg) => {
    setBusy(key); setErr('')
    try { const r = await api.post(`/queue/${id}/${path}`, path === 'confirm-arrival' ? { mode: key } : undefined); setLive(r.data); toast(msg) }
    catch (e) { setErr(errorMessage(e)) } finally { setBusy('') }
  }

  if (loading && !t) return <Spinner />
  if (error && !t) return <ErrorBox>{errorMessage(error, 'Token not found.')}</ErrorBox>
  const est = t.estimate, win = t.arrival_window
  const inQueue = ['booked', 'confirmed', 'waiting', 'approaching'].includes(t.status)
  const ended = ['cancelled', 'no_show', 'completed'].includes(t.status)
  const cancel = () => { if (confirm('Cancel this token?')) act('cancel', 'cancel', 'Token cancelled.') }

  return (
    <div className="mx-auto max-w-xl space-y-3.5">
      <div className="flex items-center justify-between">
        <Link to="/app" aria-label="Back" className="grid h-11 w-11 place-items-center rounded-full border border-line bg-white text-brand-600 hover:bg-brand-50"><ArrowLeft className="h-5 w-5" /></Link>
      </div>

      <section className="flex flex-col gap-[18px] rounded-[28px] p-[22px] text-brand-50" style={{ background: 'radial-gradient(120% 90% at 100% 0%, #2a6177 0%, #124559 55%, #0b3142 100%)' }}>
        <div className="flex items-start justify-between gap-2.5">
          <div><p className="text-[13px] text-brand-200">{t.service.service_name}{nameOf(t.service.location_id) ? ` · ${nameOf(t.service.location_id)}` : ''}</p><p className="font-display text-[64px] font-semibold leading-none tracking-tighter" aria-label={`Token ${t.token_label}`}>{t.token_label}</p></div>
          <StatusBadge status={t.status} />
        </div>
        {!ended && <Stepper status={t.status} />}
        {t.status === 'called' && <p className="flex items-center gap-3 rounded-2xl bg-brand-50 p-4 font-medium text-brand-600" role="status"><MapPin className="h-5 w-5 shrink-0" aria-hidden />It's your turn — please go to {t.counter?.counter_name}.</p>}
        {t.status === 'serving' && <p className="rounded-2xl bg-brand-50 p-4 font-medium text-brand-600">You are being served at {t.counter?.counter_name}.</p>}
        {t.status === 'cancelled' && <p className="rounded-2xl bg-brand-50/10 p-4 text-sm">This token was cancelled. You can join again from the Join page.</p>}
        {t.status === 'no_show' && <p className="rounded-2xl bg-brand-50/10 p-4 text-sm">You were called but did not arrive. You can rejoin after a short wait.</p>}
        {t.status === 'completed' && <p className="rounded-2xl bg-brand-50/10 p-4 text-sm">All done — thank you.</p>}
      </section>

      {inQueue && (
        <>
          <div className="grid grid-cols-3 gap-2.5">
            <Card className="!rounded-[20px] !p-3.5"><p className="text-xs text-muted">Ahead of you</p><p className="font-display text-3xl font-semibold leading-tight">{t.customers_ahead ?? '—'}</p></Card>
            <Card className="!rounded-[20px] !p-3.5"><p className="text-xs text-muted">Position</p><p className="font-display text-3xl font-semibold leading-tight">{t.queue_position ?? '—'}</p></Card>
            <Card className="!rounded-[20px] !p-3.5"><p className="text-xs text-muted">Counter</p><p className="text-[15px] font-semibold leading-[2]">{t.counter?.counter_name || 'Soon'}</p></Card>
          </div>

          <Card className="!rounded-3xl !p-[18px]">
            <div className="mb-3 flex items-center justify-between gap-2"><span className="text-sm font-semibold">Estimated waiting time</span><EstimateBadge estimate={est} /></div>
            {est?.wait_minutes != null ? (
              <>
                <p className="mb-4 flex items-baseline gap-2"><span className="font-display text-[52px] font-semibold leading-none tracking-tight">{Math.round(est.wait_minutes)}</span><span className="text-base text-muted">minutes</span></p>
                <RangeBar value={est.wait_minutes} lower={est.lower_minutes} upper={est.upper_minutes} />
              </>
            ) : <p className="text-base text-muted">We will estimate your wait as soon as a counter opens for this service.</p>}
            <p className="mt-3 text-xs leading-relaxed text-muted">{est?.note} Estimates refresh automatically as the queue changes.</p>
          </Card>

          {win && (
            <section className="flex items-center gap-3.5 rounded-3xl bg-brand-200 p-[18px] text-ink">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-brand-600 text-brand-50"><Clock className="h-[22px] w-[22px]" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-[#0b3142]">Recommended arrival</p>
                {t.arrival_time ? <p className="font-display text-xl font-semibold">You are checked in. Stay close to the counters.</p>
                  : win.arrive_now ? <p className="font-display text-[34px] font-semibold leading-tight tracking-tight">Head over now</p>
                  : <p className="font-display text-[34px] font-semibold leading-tight tracking-tight">{time(win.recommended_arrival)}</p>}
                {!t.arrival_time && !win.arrive_now && <p className="text-[13px] text-[#0b3142]">Window {time(win.window_start)} – {time(win.window_end)} · served around {time(win.expected_service_time)}</p>}
              </div>
            </section>
          )}

          {err && <ErrorBox>{err}</ErrorBox>}
          <div className="grid grid-cols-2 gap-2.5">
            {t.status === 'booked' ? <Button variant="ghost" className="min-h-[52px]" loading={busy === 'on_my_way'} onClick={() => act('on_my_way', 'confirm-arrival', 'Thanks — we will keep updating your window.')}><Footprints className="h-4 w-4" aria-hidden />I'm on my way</Button> : <span />}
            {!t.arrival_time && <Button className="min-h-[52px]" loading={busy === 'arrived'} onClick={() => act('arrived', 'confirm-arrival', 'Checked in.')}><MapPin className="h-4 w-4" aria-hidden />I've arrived</Button>}
          </div>
          <button type="button" onClick={cancel} disabled={busy === 'cancel'} className="min-h-11 w-full text-sm font-semibold text-[#8f1a10]">Cancel token</button>
        </>
      )}
      {t.status === 'called' && <button type="button" onClick={cancel} className="min-h-11 w-full text-sm font-semibold text-[#8f1a10]">Cancel token</button>}
    </div>
  )
}
