import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Check, MapPin, Plus, Power } from 'lucide-react'
import { api, errorMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { ORG_TYPES, orgType, useLocations } from '../../lib/location'
import { usePoll } from '../../lib/live'
import { Badge, Button, Card, CardTitle, Empty, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, useToast } from '../../components/ui'

const TIMEZONES = ['Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo', 'Europe/London', 'Europe/Berlin', 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Australia/Sydney', 'UTC']

function TypePicker({ value, onChange }) {
  return (
    <fieldset>
      <legend className="mb-2 text-xs font-semibold text-slate-600">Organization type</legend>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {Object.entries(ORG_TYPES).map(([k, t]) => {
          const Icon = t.icon
          return (
            <label key={k} className={`flex min-h-[72px] cursor-pointer flex-col justify-center gap-1 rounded-2xl border-2 px-3 py-2.5 ${value === k ? 'border-brand-600 bg-brand-50' : 'border-line bg-white hover:bg-slate-50'}`}>
              <input type="radio" name="org-type" value={k} checked={value === k} onChange={() => onChange(k)} className="sr-only" />
              <span className="flex items-center gap-2 text-sm font-semibold"><Icon className="h-[18px] w-[18px] text-brand-600" aria-hidden />{t.label}</span>
              <span className="text-[11px] leading-snug text-muted">{t.hint}</span>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

function OrgForm({ initial, templates, onSubmit, onCancel, submitLabel, creating }) {
  const [f, setF] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const tpl = templates?.[f.location_type]
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await onSubmit({ ...f, address: f.address || null, open_time: f.open_time || null, close_time: f.close_time || null }) }
    catch (x) { setErr(errorMessage(x)) } finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      {err && <ErrorBox>{err}</ErrorBox>}
      <Field label="Name"><Input required minLength={2} maxLength={120} placeholder="e.g. City General Hospital" value={f.name} onChange={set('name')} /></Field>
      <TypePicker value={f.location_type} onChange={(k) => setF({ ...f, location_type: k, open_time: '', close_time: '' })} />
      <Field label="Address (optional)"><Input maxLength={300} placeholder="Street, city" value={f.address || ''} onChange={set('address')} /></Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="Opens"><Input type="time" value={f.open_time || tpl?.open_time || ''} onChange={set('open_time')} /></Field>
        <Field label="Closes"><Input type="time" value={f.close_time || tpl?.close_time || ''} onChange={set('close_time')} /></Field>
        <Field label="Timezone">
          <Input list="tz-list" value={f.timezone} onChange={set('timezone')} />
          <datalist id="tz-list">{TIMEZONES.map((z) => <option key={z} value={z} />)}</datalist>
        </Field>
      </div>
      {creating && tpl && (
        <div className="rounded-2xl bg-brand-50 p-4">
          <label className="flex cursor-pointer items-start gap-3 text-sm font-semibold"><input type="checkbox" className="mt-0.5 h-5 w-5 accent-[#124559]" checked={f.use_template} onChange={(e) => setF({ ...f, use_template: e.target.checked })} />
            <span>Start with typical services and {tpl.counters} counters<span className="block text-xs font-normal text-muted">Everything is editable afterwards. Counters start closed.</span></span></label>
          {f.use_template && <ul className="mt-3 flex flex-wrap gap-1.5">{tpl.services.map((s) => <li key={s.code} className="rounded-full bg-white px-3 py-1 text-xs font-medium text-brand-600 ring-1 ring-brand-200">{s.service_name} · ~{s.average_service_duration} min</li>)}</ul>}
        </div>
      )}
      <div className="flex justify-end gap-2 pt-1"><Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button><Button type="submit" loading={busy}>{submitLabel}</Button></div>
    </form>
  )
}

function ServicesPanel({ org }) {
  const toast = useToast()
  const svcs = usePoll(() => api.get('/admin/services').then((r) => r.data), [org.location_id])
  const [f, setF] = useState({ service_name: '', code: '', average_service_duration: 8, description: '' })
  const [err, setErr] = useState('')
  const guard = async (fn, ok) => { setErr(''); try { await fn(); if (ok) toast(ok); svcs.reload() } catch (e) { setErr(errorMessage(e)) } }
  return (
    <Card>
      <CardTitle sub={`Services customers can queue for at ${org.name}. Paused services are hidden from customers.`}>Services</CardTitle>
      {err && <div className="mb-3"><ErrorBox>{err}</ErrorBox></div>}
      {svcs.loading ? <Spinner /> : !svcs.data?.length ? <Empty title="No services yet">Add the first one below. Customers cannot join until at least one service and one open counter exist.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-2 font-semibold">Service</th><th className="py-2 font-semibold">Code</th><th className="py-2 font-semibold">Typical minutes</th><th className="py-2 font-semibold">Status</th></tr></thead>
            <tbody className="divide-y divide-line">
              {svcs.data.map((s) => (
                <tr key={s.service_id}>
                  <td className="py-3 pr-3"><span className="font-medium">{s.service_name}</span><span className="block text-xs text-muted">{s.description}</span></td>
                  <td className="py-3"><Badge tone="blue">{s.code}</Badge></td>
                  <td className="py-3"><input type="number" min="1" max="240" step="0.5" defaultValue={s.average_service_duration} aria-label={`Typical minutes for ${s.service_name}`}
                    onBlur={(e) => Number(e.target.value) !== s.average_service_duration && guard(() => api.patch(`/admin/services/${s.service_id}`, { average_service_duration: Number(e.target.value) }), 'Saved')}
                    className="min-h-10 w-24 rounded-xl border border-brand-200 px-3 text-sm focus:border-brand-600 focus:outline-none" /></td>
                  <td className="py-3"><Select className="!w-36 !py-1.5" value={s.status} onChange={(e) => guard(() => api.patch(`/admin/services/${s.service_id}`, { status: e.target.value }), 'Service updated')}><option value="active">Active</option><option value="paused">Paused</option><option value="archived">Archived</option></Select></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form className="mt-5 grid gap-2 border-t border-line pt-5 sm:grid-cols-[2fr_1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); guard(async () => { await api.post('/admin/services', { ...f, average_service_duration: Number(f.average_service_duration), description: f.description || null }); setF({ service_name: '', code: '', average_service_duration: 8, description: '' }) }, 'Service added') }}>
        <Input required minLength={2} placeholder="Service name, e.g. Radiology" aria-label="Service name" value={f.service_name} onChange={(e) => setF({ ...f, service_name: e.target.value })} />
        <Input required maxLength={3} placeholder="Code" aria-label="Token code (1–3 characters)" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
        <Input required type="number" min="1" max="240" step="0.5" aria-label="Typical minutes per customer" value={f.average_service_duration} onChange={(e) => setF({ ...f, average_service_duration: e.target.value })} />
        <Button type="submit"><Plus className="h-4 w-4" aria-hidden />Add</Button>
      </form>
      <p className="mt-2 text-xs text-muted">Typical minutes are only a starting estimate. Once real services are completed, measured times take over.</p>
    </Card>
  )
}

export default function Organizations() {
  const { user } = useAuth()
  const admin = user.role === 'admin'
  const toast = useToast()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { locations, current, currentLocation, setCurrent, reload } = useLocations()
  const tpls = usePoll(() => (admin ? api.get('/admin/location-templates').then((r) => r.data) : Promise.resolve(null)), [admin])
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(null)
  // survives the page remount that happens when the selected organization changes
  const [justCreated, setJustCreatedState] = useState(() => { try { return JSON.parse(sessionStorage.getItem('queueless.justCreated')) } catch { return null } })
  const setJustCreated = (v) => { setJustCreatedState(v); if (v) sessionStorage.setItem('queueless.justCreated', JSON.stringify(v)); else sessionStorage.removeItem('queueless.justCreated') }
  useEffect(() => { if (params.get('new') === '1' && admin) { setAdding(true); setParams({}, { replace: true }) } }, [params, admin, setParams])

  const create = async (body) => {
    const r = await api.post('/admin/locations', body)
    await reload(); setAdding(false); setJustCreated(r.data); setCurrent(r.data.location_id)
    toast(`${r.data.name} added`)
  }
  const edit = async (body) => {
    await api.patch(`/admin/locations/${editing.location_id}`, { name: body.name, location_type: body.location_type, address: body.address, timezone: body.timezone, open_time: body.open_time, close_time: body.close_time })
    await reload(); setEditing(null); toast('Organization updated')
  }
  const toggle = async (o) => {
    try { await api.patch(`/admin/locations/${o.location_id}`, { is_active: !o.is_active }); await reload(); toast(o.is_active ? `${o.name} deactivated` : `${o.name} activated`) }
    catch (e) { toast(errorMessage(e), 'error') }
  }

  if (!locations) return <Spinner />
  return (
    <>
      <PageHeader title="Organizations" sub={admin ? 'Each hospital, college, bank or office runs its own services, counters, staff and thresholds.' : 'The organization you work at.'}
        actions={admin && <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" aria-hidden />Add organization</Button>} />

      {justCreated && (
        <Card className="mb-5 !border-brand-200 !bg-brand-50">
          <p className="font-display text-lg font-semibold">{justCreated.name} is ready to configure</p>
          <p className="mt-1 text-sm text-muted">{justCreated.created.services ? `${justCreated.created.services} services and ${justCreated.created.counters} counters were created (counters are closed). ` : 'No services were created. '}Next: add staff, open a counter, then share the app with your customers.</p>
          <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" onClick={() => navigate('/admin/counters')}>Set up counters &amp; staff</Button><Button size="sm" variant="ghost" onClick={() => setJustCreated(null)}>Dismiss</Button></div>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {locations.map((o) => {
          const T = orgType(o.location_type)
          const active = o.location_id === current
          return (
            <Card key={o.location_id} className={`flex flex-col gap-4 !p-5 ${active ? '!border-brand-600 ring-2 ring-brand-600/15' : ''}`}>
              <div className="flex items-start gap-3">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-brand-100 text-brand-600"><T.icon className="h-6 w-6" aria-hidden /></span>
                <div className="min-w-0 flex-1"><h3 className="truncate font-display text-lg font-semibold">{o.name}</h3><p className="text-xs text-muted">{T.label}</p></div>
                {!o.is_active && <Badge tone="slate">Inactive</Badge>}
                {active && <Badge tone="blue"><Check className="h-3 w-3" aria-hidden />Selected</Badge>}
              </div>
              {o.address && <p className="flex items-start gap-1.5 text-[13px] text-muted"><MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{o.address}</p>}
              <dl className="grid grid-cols-4 gap-2 text-center">
                {[['Services', o.services], ['Counters', o.counters], ['Staff', o.staff], ['Waiting', o.waiting]].map(([k, v]) => <div key={k} className="rounded-xl bg-slate-50 px-1 py-2"><dt className="text-[11px] text-muted">{k}</dt><dd className="font-display text-lg font-semibold">{v}</dd></div>)}
              </dl>
              <p className="text-xs text-muted">Open {o.open_time} – {o.close_time} · {o.timezone}</p>
              <div className="mt-auto flex flex-wrap gap-2">
                {!active && o.is_active && <Button size="sm" onClick={() => setCurrent(o.location_id)}>Manage</Button>}
                {admin && <Button size="sm" variant="ghost" onClick={() => setEditing(o)}>Edit</Button>}
                {admin && <Button size="sm" variant="ghost" onClick={() => toggle(o)}><Power className="h-3.5 w-3.5" aria-hidden />{o.is_active ? 'Deactivate' : 'Activate'}</Button>}
              </div>
            </Card>
          )
        })}
      </div>

      {admin && currentLocation && <div className="mt-6"><ServicesPanel key={currentLocation.location_id} org={currentLocation} /></div>}

      <Modal open={adding} onClose={() => setAdding(false)} title="Add organization">
        {adding && <OrgForm creating templates={tpls.data} submitLabel="Create organization" onCancel={() => setAdding(false)} onSubmit={create}
          initial={{ name: '', location_type: 'hospital', address: '', timezone: currentLocation?.timezone || 'Asia/Kolkata', open_time: '', close_time: '', use_template: true }} />}
      </Modal>
      <Modal open={!!editing} onClose={() => setEditing(null)} title="Edit organization">
        {editing && <OrgForm templates={tpls.data} submitLabel="Save changes" onCancel={() => setEditing(null)} onSubmit={edit}
          initial={{ name: editing.name, location_type: editing.location_type, address: editing.address || '', timezone: editing.timezone, open_time: editing.open_time, close_time: editing.close_time, use_template: false }} />}
      </Modal>
    </>
  )
}
