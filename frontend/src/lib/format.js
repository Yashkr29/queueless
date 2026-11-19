export const time = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—')
export const dateTime = (iso) => (iso ? new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—')
export const mins = (m) => (m == null ? '—' : `${Math.round(m)} min`)
export const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)

export const STATUS = {
  booked: { label: 'Booked', tone: 'slate' },
  confirmed: { label: 'On the way', tone: 'blue' },
  waiting: { label: 'Waiting', tone: 'amber' },
  approaching: { label: 'Approaching turn', tone: 'violet' },
  called: { label: 'Called', tone: 'green' },
  serving: { label: 'Serving', tone: 'green' },
  completed: { label: 'Completed', tone: 'slate' },
  cancelled: { label: 'Cancelled', tone: 'red' },
  no_show: { label: 'No-show', tone: 'red' },
}
export const PRIORITIES = [
  { value: 'none', label: 'Regular' },
  { value: 'senior', label: 'Senior citizen' },
  { value: 'disabled', label: 'Person with disability' },
  { value: 'pregnant', label: 'Pregnant' },
]
