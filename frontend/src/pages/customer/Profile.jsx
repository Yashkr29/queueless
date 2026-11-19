import { useState } from 'react'
import { api, errorMessage } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { Button, Card, CardTitle, ErrorBox, Field, Input, PageHeader, useToast } from '../../components/ui'

export default function Profile() {
  const { user, setUser } = useAuth()
  const toast = useToast()
  const [f, setF] = useState({ name: user.name, phone: user.phone || '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { const r = await api.patch('/auth/me', { name: f.name, phone: f.phone }); setUser(r.data); toast('Profile saved') }
    catch (x) { setErr(errorMessage(x)) } finally { setBusy(false) }
  }
  return (
    <>
      <PageHeader title="Profile" sub="Your details are only visible to you and, by name, to the staff serving you." />
      <Card className="max-w-xl">
        <CardTitle>Account</CardTitle>
        <form onSubmit={save} className="space-y-4">
          {err && <ErrorBox>{err}</ErrorBox>}
          <Field label="Full name"><Input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Email" hint="Email cannot be changed here."><Input value={user.email} disabled /></Field>
          <Field label="Phone"><Input type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
          <Button type="submit" loading={busy}>Save changes</Button>
        </form>
      </Card>
    </>
  )
}
