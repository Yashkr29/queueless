import { api } from './api'

/** Applies a recommendation's `action` payload from the optimizer. The admin always clicks; nothing auto-applies. */
export function applyAction(action) {
  if (action.type === 'open_counter') return api.patch(`/admin/counters/${action.counter_id}`, { status: 'open' })
  if (action.type === 'add_service') return api.patch(`/admin/counters/${action.counter_id}`, { service_ids: action.service_ids })
  return Promise.reject(new Error('Unknown action'))
}
