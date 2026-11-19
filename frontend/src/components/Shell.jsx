import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Bell, Building2, Check, ChevronsUpDown, LogOut, Plus } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'
import { LiveProvider, useDebounced, useLiveEvent, useLiveStatus, usePoll } from '../lib/live'
import { LocationProvider, orgType, useLocations } from '../lib/location'
import { Spinner, useToast } from './ui'

const MARK = (stroke, dot) => (
  <svg viewBox="0 0 32 32" className="h-[22px] w-[22px]" aria-hidden><path d="M9 11h10M9 16h14M9 21h8" stroke={stroke} strokeWidth="2.8" strokeLinecap="round" /><circle cx="23" cy="21" r="2.8" fill={dot} /></svg>
)

export function Logo({ dark }) {
  return (
    <span className="flex items-center gap-3">
      <span className={`grid h-10 w-10 place-items-center rounded-xl ${dark ? 'bg-brand-50' : 'bg-brand-600'}`}>{dark ? MARK('#124559', '#598392') : MARK('#eff6e0', '#aec3b0')}</span>
      <span className={`font-display text-[22px] font-semibold tracking-tight ${dark ? 'text-brand-50' : 'text-ink'}`}>QueueLess</span>
    </span>
  )
}

function LivePill() {
  const on = useLiveStatus()
  return (
    <span className={`hidden items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-semibold sm:inline-flex ${on ? 'border-line bg-white text-brand-600' : 'border-line bg-white text-muted'}`}>
      <span className={`h-2 w-2 rounded-full ${on ? 'bg-brand-600 shadow-[0_0_0_4px_rgba(18,69,89,0.15)]' : 'bg-slate-300'}`} />{on ? 'Live' : 'Reconnecting…'}
    </span>
  )
}

function BellButton({ customer }) {
  const toast = useToast()
  const navigate = useNavigate()
  const { data, reload } = usePoll(() => (customer ? api.get('/notifications?limit=1').then((r) => r.data) : Promise.resolve({ unread: 0 })), [customer], 60000)
  useLiveEvent((m) => { if (m.type === 'notification') { toast(`${m.notification.title}: ${m.notification.message}`); reload() } })
  if (!customer) return null
  return (
    <button onClick={() => navigate('/app/notifications')} className="relative grid h-11 w-11 place-items-center rounded-full border border-line bg-white text-brand-600 hover:bg-brand-50" aria-label={`Notifications${data?.unread ? `, ${data.unread} unread` : ''}`}>
      <Bell className="h-5 w-5" />
      {data?.unread > 0 && <span className="absolute right-2.5 top-2.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-600" />}
    </button>
  )
}

/** Sidebar widgets for staff: live badges + honest model status. */
function useStaffSignals(staff) {
  const { current } = useLocations()
  const queue = usePoll(() => (staff ? api.get('/admin/queue?page_size=1').then((r) => r.data) : Promise.resolve(null)), [staff, current], 30000)
  const alerts = usePoll(() => (staff ? api.get('/admin/alerts').then((r) => r.data) : Promise.resolve(null)), [staff, current], 30000)
  const models = usePoll(() => (staff ? api.get('/predictions/models').then((r) => r.data) : Promise.resolve(null)), [staff, current], 300000)
  const settings = usePoll(() => (staff ? api.get('/admin/settings').then((r) => r.data) : Promise.resolve(null)), [staff, current], 300000)
  const refreshLive = useDebounced(() => { queue.reload(); alerts.reload() }, 2500)
  useLiveEvent((m) => { if (m.type === 'queue_changed') refreshLive() })
  return { queue: queue.data?.total, alerts: alerts.data?.alerts?.length, model: models.data?.wait_time, hours: settings.data?.settings }
}

function LocationSwitcher({ admin, staff }) {
  const { locations, currentLocation, setCurrent } = useLocations()
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  if (!currentLocation) return null
  const T = orgType(currentLocation.location_type)
  const canSwitch = admin || (!staff && locations.length > 1)
  const sub = currentLocation.open_time ? `${T.label} · ${currentLocation.open_time} – ${currentLocation.close_time}` : T.label
  const head = (
    <>
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-50/15"><T.icon className="h-[18px] w-[18px]" aria-hidden /></span>
      <span className="flex min-w-0 flex-1 flex-col text-left"><span className="truncate text-sm font-semibold">{currentLocation.name}</span><span className="truncate text-xs text-brand-200">{sub}</span></span>
      {canSwitch && <ChevronsUpDown className="h-4 w-4 shrink-0 text-brand-200" aria-hidden />}
    </>
  )
  if (!canSwitch) return <div className="flex min-h-14 items-center gap-3 rounded-2xl border border-brand-200/30 bg-brand-50/[0.07] px-3 py-2.5">{head}</div>
  return (
    <div className="rounded-2xl border border-brand-200/30 bg-brand-50/[0.07]">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex min-h-14 w-full items-center gap-3 px-3 py-2.5">{head}</button>
      {open && (
        <div className="border-t border-brand-200/20 p-1.5">
          <ul className="max-h-56 overflow-y-auto" aria-label="Organizations">
            {locations.map((l) => {
              const Icon = orgType(l.location_type).icon
              const on = l.location_id === currentLocation.location_id
              return (
                <li key={l.location_id}>
                  <button type="button" onClick={() => { setCurrent(l.location_id); setOpen(false) }} className={`flex min-h-11 w-full items-center gap-2.5 rounded-xl px-2.5 text-left text-sm ${on ? 'bg-brand-50 text-brand-600' : 'text-[#d5e3d3] hover:bg-brand-50/10'}`}>
                    <Icon className="h-4 w-4 shrink-0" aria-hidden /><span className="flex-1 truncate">{l.name}</span>{!l.is_active && <span className="text-[10px] uppercase tracking-wide opacity-70">inactive</span>}{on && <Check className="h-4 w-4" aria-hidden />}
                  </button>
                </li>
              )
            })}
          </ul>
          {admin && (
            <div className="mt-1 flex flex-col gap-1 border-t border-brand-200/20 pt-1.5">
              <button type="button" onClick={() => { setOpen(false); navigate('/admin/organizations?new=1') }} className="flex min-h-11 items-center gap-2.5 rounded-xl px-2.5 text-sm font-semibold text-brand-50 hover:bg-brand-50/10"><Plus className="h-4 w-4" aria-hidden />Add organization</button>
              <button type="button" onClick={() => { setOpen(false); navigate('/admin/organizations') }} className="flex min-h-11 items-center gap-2.5 rounded-xl px-2.5 text-sm text-[#d5e3d3] hover:bg-brand-50/10"><Building2 className="h-4 w-4" aria-hidden />Manage organizations</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Sidebar({ nav, user, onSignOut }) {
  const staff = user.role !== 'customer'
  const s = useStaffSignals(staff)
  const badge = (to) => (to === '/admin/queue' ? s.queue : to === '/admin/forecast' ? s.alerts : null)
  const initials = user.name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <aside className="fixed bottom-4 left-4 top-4 z-30 hidden w-[256px] flex-col gap-6 overflow-y-auto rounded-[28px] bg-brand-600 p-5 text-brand-50 lg:flex">
      <div className="px-2"><Logo dark /></div>
      <LocationSwitcher admin={user.role === 'admin'} staff={staff} />
      <nav className="flex flex-col gap-1" aria-label={staff ? 'Operations' : 'Customer'}>
        <span className="px-3 pb-2 text-[11px] uppercase tracking-[0.12em] text-brand-200">{staff ? 'Operations' : 'Menu'}</span>
        {nav.filter((n) => !n.adminOnly || user.role === 'admin').map(({ to, icon: Icon, label, end }) => {
          const b = badge(to)
          return (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex min-h-11 items-center gap-3 rounded-2xl px-3 text-sm font-medium transition-colors ${isActive ? 'bg-brand-50 text-brand-600' : 'text-[#d5e3d3] hover:bg-brand-50/10'}`}>
              <Icon className="h-5 w-5" aria-hidden /><span className="flex-1">{label}</span>
              {b ? <span className="min-w-[22px] rounded-full bg-brand-200 px-2 py-0.5 text-center text-xs font-semibold text-ink">{b}</span> : null}
            </NavLink>
          )
        })}
      </nav>
      <div className="flex-1" />
      {staff && (
        <div className="rounded-[18px] border border-brand-200/20 bg-brand-50/[0.07] p-4">
          <p className="flex items-center gap-2 text-[13px] font-semibold"><span className="h-2 w-2 rounded-full bg-brand-200 shadow-[0_0_0_4px_rgba(174,195,176,0.25)]" />{s.model ? 'Predictions online' : 'Predictions offline'}</p>
          <p className="mt-2 text-xs leading-relaxed text-brand-200">{s.model ? (s.model.trained_on === 'synthetic' ? 'Wait-time model is trained on simulated data. Real accuracy appears after real services are completed.' : 'Wait-time model is trained on real service data.') : 'No model loaded. Customers see a labelled standard estimate instead.'}</p>
        </div>
      )}
      <div className="flex items-center gap-3 px-1">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-500 text-sm font-semibold text-brand-50">{initials}</span>
        <span className="min-w-0 flex-1 leading-tight"><span className="block truncate text-sm font-semibold">{user.name}</span><span className="block text-xs capitalize text-brand-200">{user.role}</span></span>
        <button onClick={onSignOut} title="Sign out" aria-label="Sign out" className="grid h-10 w-10 place-items-center rounded-full text-brand-200 hover:bg-brand-50/10 hover:text-white"><LogOut className="h-[18px] w-[18px]" /></button>
      </div>
    </aside>
  )
}

function ShellInner({ nav, area }) {
  const { user, logout } = useAuth()
  const { locations, current } = useLocations()
  const navigate = useNavigate()
  const out = () => { logout(); navigate('/') }
  if (!locations) return <Spinner label="Loading your organization…" />
  return (
    <LiveProvider>
      <div className="min-h-full p-3 lg:p-4">
        <Sidebar nav={nav} user={user} onSignOut={out} />
        <div className="lg:pl-[272px]">
          <header className="mb-6 flex items-center justify-between gap-3 px-1 pt-1">
            <div className="lg:hidden"><Logo /></div>
            <p className="hidden text-xs font-semibold uppercase tracking-[0.14em] text-muted lg:block">{area}</p>
            <div className="flex items-center gap-3"><LivePill /><BellButton customer={user.role === 'customer'} /></div>
          </header>
          <main key={current} className="mx-auto max-w-[1280px] px-1 pb-28 lg:pb-8"><Outlet /></main>
        </div>

        <nav className="fixed inset-x-3 bottom-3 z-30 flex gap-1 overflow-x-auto rounded-[28px] bg-brand-600 p-2 lg:hidden" aria-label={`${area} navigation`}>
          {nav.filter((n) => !n.adminOnly || user.role === 'admin').map(({ to, icon: Icon, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex min-h-[52px] min-w-[68px] flex-1 flex-col items-center justify-center gap-0.5 rounded-[20px] px-2 text-[11px] font-medium ${isActive ? 'bg-brand-50 text-brand-600' : 'text-[#d5e3d3]'}`}>
              <Icon className="h-5 w-5" aria-hidden />{label}
            </NavLink>
          ))}
          <button onClick={out} className="flex min-h-[52px] min-w-[68px] flex-1 flex-col items-center justify-center gap-0.5 rounded-[20px] px-2 text-[11px] font-medium text-[#d5e3d3]"><LogOut className="h-5 w-5" aria-hidden />Sign out</button>
        </nav>
      </div>
    </LiveProvider>
  )
}

export function Shell(props) {
  return (
    <LocationProvider>
      <ShellInner {...props} />
    </LocationProvider>
  )
}
