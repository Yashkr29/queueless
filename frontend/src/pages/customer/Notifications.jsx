import { Bell } from 'lucide-react'
import { api } from '../../lib/api'
import { useLiveEvent, usePoll } from '../../lib/live'
import { dateTime } from '../../lib/format'
import { Button, Card, Empty, PageHeader, Spinner } from '../../components/ui'

export default function Notifications() {
  const { data, loading, reload } = usePoll(() => api.get('/notifications').then((r) => r.data), [])
  useLiveEvent((m) => { if (m.type === 'notification') reload() })
  const readAll = async () => { await api.post('/notifications/read-all'); reload() }
  return (
    <>
      <PageHeader title="Notifications" sub="Updates about your tokens." actions={data?.unread > 0 && <Button variant="ghost" size="sm" onClick={readAll}>Mark all as read</Button>} />
      <Card className="!p-0 overflow-hidden">
        {loading ? <Spinner /> : !data?.items.length ? <Empty icon={Bell} title="Nothing yet">Booking confirmations, arrival reminders and delay notices will show up here.</Empty> : (
          <ul className="divide-y divide-line">
            {data.items.map((n) => (
              <li key={n.notification_id} className={`flex gap-3 px-5 py-4 ${n.read ? '' : 'bg-brand-50/40'}`}>
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.read ? 'bg-transparent' : 'bg-brand-600'}`} aria-label={n.read ? undefined : 'Unread'} />
                <div className="min-w-0 flex-1"><p className="text-sm font-medium">{n.title}</p><p className="mt-0.5 text-sm text-slate-600">{n.message}</p></div>
                <time className="shrink-0 text-xs text-muted">{dateTime(n.created_at)}</time>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  )
}
