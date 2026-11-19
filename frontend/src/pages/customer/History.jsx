import { Link } from 'react-router-dom'
import { History as HistoryIcon } from 'lucide-react'
import { api } from '../../lib/api'
import { usePoll } from '../../lib/live'
import { dateTime } from '../../lib/format'
import { Card, Empty, PageHeader, Spinner, StatusBadge } from '../../components/ui'

export default function Tokens() {
  const { data, loading } = usePoll(() => api.get('/queue/mine?limit=100').then((r) => r.data), [])
  return (
    <>
      <PageHeader title="Booking history" sub="Your recent tokens, newest first." />
      <Card className="!p-0 overflow-hidden">
        {loading ? <Spinner /> : !data?.length ? <Empty icon={HistoryIcon} title="No bookings yet">Your tokens will appear here once you join a queue.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="bg-surface text-xs text-muted"><tr><th className="px-5 py-3 font-medium">Token</th><th className="px-5 py-3 font-medium">Service</th><th className="px-5 py-3 font-medium">Joined</th><th className="px-5 py-3 font-medium">Status</th></tr></thead>
              <tbody className="divide-y divide-line">
                {data.map((t) => (
                  <tr key={t.token_id} className="hover:bg-slate-50/60">
                    <td className="px-5 py-3.5 font-semibold"><Link className="text-brand-700 hover:underline" to={`/app/token/${t.token_id}`}>{t.token_label}</Link></td>
                    <td className="px-5 py-3.5">{t.service.service_name}</td>
                    <td className="px-5 py-3.5 text-muted">{dateTime(t.created_at)}</td>
                    <td className="px-5 py-3.5"><StatusBadge status={t.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  )
}
