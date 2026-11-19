import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Building2, GraduationCap, Hospital, Landmark, Store } from 'lucide-react'
import { api, getActiveLocation, setActiveLocation } from './api'
import { useAuth } from './auth'

/** Organization types an admin can add. Labels match the backend templates (backend/app/services/org_templates.py). */
export const ORG_TYPES = {
  hospital: { icon: Hospital, label: 'Hospital / clinic', hint: 'OPD, lab, pharmacy, registration' },
  college: { icon: GraduationCap, label: 'College / university', hint: 'Admissions, fees, exams, records' },
  bank: { icon: Landmark, label: 'Bank branch', hint: 'Cash, accounts, loans, support' },
  government: { icon: Building2, label: 'Government centre', hint: 'Applications, verification, payments' },
  other: { icon: Store, label: 'Other service centre', hint: 'A general service desk' },
}
export const orgType = (t) => ORG_TYPES[t] || ORG_TYPES.other

const Ctx = createContext(null)
export const useLocations = () => useContext(Ctx)

/**
 * Loads the organizations the signed-in user may use and keeps the selected one in localStorage.
 * api.js sends it as `X-Location-Id` on every request; staff are pinned to their own organization by the server.
 */
export function LocationProvider({ children }) {
  const { user } = useAuth()
  const [locations, setLocations] = useState(null)
  const [current, setCurrentState] = useState(getActiveLocation())

  const load = useCallback(async () => {
    const r = await api.get(user.role === 'customer' ? '/locations' : '/admin/locations')
    const list = r.data
    const stored = Number(getActiveLocation())
    const resolved = list.find((l) => l.location_id === stored) || list[0]
    if (resolved) setActiveLocation(resolved.location_id)
    setCurrentState(resolved ? String(resolved.location_id) : null)
    setLocations(list)
    return list
  }, [user.role])

  useEffect(() => { load().catch(() => setLocations([])) }, [load, user.user_id])

  const value = useMemo(() => ({
    locations, reload: load, current: current ? Number(current) : null,
    currentLocation: locations?.find((l) => String(l.location_id) === String(current)) || null,
    nameOf: (id) => locations?.find((l) => l.location_id === id)?.name,
    setCurrent: (id) => { setActiveLocation(id); setCurrentState(String(id)) },
  }), [locations, current, load])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
