import { useEffect, useState } from 'react'
import type { TenantInvitationItem } from '../api/types'

interface Props {
  open: boolean
  loading: boolean
  onClose: () => void
  onInvite: (
    email: string,
    role: 'member' | 'admin',
    expiresInHours: number,
  ) => Promise<{
    inviteCode: string
    inviteLink: string
    emailSent: boolean
    emailError?: string | null
  }>
  onLoadPending: () => Promise<TenantInvitationItem[]>
}

export default function InviteMemberModal({ open, loading, onClose, onInvite, onLoadPending }: Props) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<'member' | 'admin'>('member')
  const [expiresInHours, setExpiresInHours] = useState(72)
  const [inviteCode, setInviteCode] = useState('')
  const [inviteLinkFromApi, setInviteLinkFromApi] = useState('')
  const [deliveryNote, setDeliveryNote] = useState('')
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<TenantInvitationItem[]>([])

  useEffect(() => {
    if (!open) return
    onLoadPending().then(setPending).catch(() => setPending([]))
  }, [open, onLoadPending])

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setInviteCode('')
    setInviteLinkFromApi('')
    setDeliveryNote('')
    setCopied(false)
    try {
      const result = await onInvite(email.trim(), role, expiresInHours)
      setInviteCode(result.inviteCode)
      setInviteLinkFromApi(result.inviteLink)
      setDeliveryNote(result.emailSent ? 'Email sent successfully.' : `Email not sent: ${result.emailError || 'disabled'}`)
      const list = await onLoadPending()
      setPending(list)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const inviteLink = inviteCode ? inviteLinkFromApi || buildInviteLink(inviteCode) : ''

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-xl rounded-2xl border border-gray-700 bg-gray-900 p-5 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-100">Invite Member</h2>
          <button className="text-sm text-gray-400 hover:text-white" onClick={onClose} type="button">
            Close
          </button>
        </div>

        <form onSubmit={submit} className="mt-4 space-y-3">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="invitee@example.com"
            className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as 'member' | 'admin')}
              className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
            >
              <option value="member">member</option>
              <option value="admin">admin</option>
            </select>
            <input
              type="number"
              min={1}
              max={720}
              value={expiresInHours}
              onChange={(e) => setExpiresInHours(Math.max(1, Math.min(720, Number(e.target.value) || 72)))}
              className="rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm"
            />
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          {inviteCode && (
            <div className="space-y-2">
              {deliveryNote && <p className="text-xs text-gray-400">{deliveryNote}</p>}
              <p className="text-sm text-emerald-300 break-all">
                Invite code: <span className="font-mono">{inviteCode}</span>
              </p>
              <div className="rounded-lg border border-gray-700 bg-gray-950 p-2">
                <p className="text-[11px] text-gray-400 mb-1">Email link</p>
                <p className="text-xs text-gray-200 break-all font-mono">{inviteLink}</p>
                <button
                  type="button"
                  className="mt-2 rounded-md border border-emerald-700 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-900/30"
                  onClick={() => {
                    void copyToClipboard(inviteLink).then((ok) => {
                      setCopied(ok)
                    })
                  }}
                >
                  {copied ? 'Copied' : 'Copy Invite Link'}
                </button>
              </div>
            </div>
          )}
          <button
            type="submit"
            disabled={loading || !email.trim()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-40"
          >
            {loading ? 'Inviting...' : 'Create Invitation'}
          </button>
        </form>

        <div className="mt-5">
          <h3 className="text-sm font-medium text-gray-300">Pending Invitations</h3>
          <div className="mt-2 max-h-40 overflow-auto space-y-1 pr-1">
            {pending.length === 0 && <p className="text-xs text-gray-500">No pending invitations</p>}
            {pending.map((item) => (
              <div key={item.invitation_id} className="rounded-md border border-gray-800 px-2 py-1 text-xs text-gray-300">
                <div>{item.invitee_email}</div>
                <div className="font-mono text-gray-400">{item.invite_code}</div>
                <button
                  type="button"
                  className="mt-1 rounded border border-gray-700 px-1.5 py-0.5 text-[11px] text-gray-200 hover:bg-gray-800"
                  onClick={() => {
                    void copyToClipboard(buildInviteLink(item.invite_code))
                  }}
                >
                  Copy Link
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function buildInviteLink(inviteCode: string): string {
  try {
    return `${window.location.origin}/accept-invite?code=${encodeURIComponent(inviteCode)}`
  } catch {
    return `/accept-invite?code=${encodeURIComponent(inviteCode)}`
  }
}

async function copyToClipboard(text: string): Promise<boolean> {
  if (!text) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // fallback below
  }

  try {
    const area = document.createElement('textarea')
    area.value = text
    area.style.position = 'fixed'
    area.style.left = '-9999px'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(area)
    return ok
  } catch {
    return false
  }
}
