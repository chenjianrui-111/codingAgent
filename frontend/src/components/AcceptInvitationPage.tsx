import { useEffect, useMemo, useRef, useState } from 'react'
import type { AuthTenantInfo } from '../api/types'

interface Props {
  authenticated: boolean
  currentTenant: AuthTenantInfo | null
  onBackToChat: () => void
  onAccept: (inviteCode: string) => Promise<AuthTenantInfo>
}

export default function AcceptInvitationPage({
  authenticated,
  currentTenant,
  onBackToChat,
  onAccept,
}: Props) {
  const [inviteCode, setInviteCode] = useState(() => getInviteCodeFromUrl())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AuthTenantInfo | null>(null)
  const triedAuto = useRef(false)

  const disabled = useMemo(() => !authenticated || loading || !inviteCode.trim(), [authenticated, loading, inviteCode])

  useEffect(() => {
    if (!authenticated || !inviteCode.trim() || triedAuto.current) return
    triedAuto.current = true
    void accept(inviteCode.trim(), true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authenticated, inviteCode])

  const accept = async (code: string, auto: boolean) => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const tenant = await onAccept(code)
      setResult(tenant)
      if (auto) {
        window.setTimeout(() => {
          onBackToChat()
        }, 900)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inviteCode.trim()) return
    await accept(inviteCode.trim(), false)
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 px-4 py-10">
      <div className="mx-auto w-full max-w-2xl rounded-2xl border border-gray-800 bg-gray-900 p-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Accept Tenant Invitation</h1>
          <button className="text-sm text-blue-300 hover:text-blue-200" onClick={onBackToChat} type="button">
            Back To Chat
          </button>
        </div>
        <p className="mt-2 text-sm text-gray-400">
          Current tenant: {currentTenant ? `${currentTenant.tenant_name} (${currentTenant.role})` : 'Not selected'}
        </p>

        {!authenticated && (
          <p className="mt-4 rounded-lg border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
            Sign in first, then return to this page to accept the invitation.
          </p>
        )}
        {authenticated && inviteCode.trim() && !result && loading && (
          <p className="mt-4 rounded-lg border border-blue-700/50 bg-blue-950/30 px-3 py-2 text-sm text-blue-200">
            Accepting invitation automatically...
          </p>
        )}

        <form onSubmit={submit} className="mt-4 space-y-3">
          <input
            value={inviteCode}
            onChange={(e) => setInviteCode(e.target.value)}
            placeholder="inv_xxx"
            className="w-full rounded-lg border border-gray-700 bg-gray-950 px-3 py-2 text-sm font-mono"
          />
          {error && <p className="text-sm text-red-400">{error}</p>}
          {result && (
            <p className="text-sm text-emerald-300">
              Joined tenant: <strong>{result.tenant_name}</strong> ({result.role}). Redirecting to chat...
            </p>
          )}
          <button
            type="submit"
            disabled={disabled}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
          >
            {loading ? 'Accepting...' : 'Accept Invitation'}
          </button>
        </form>
      </div>
    </div>
  )
}

function getInviteCodeFromUrl(): string {
  try {
    const url = new URL(window.location.href)
    return url.searchParams.get('code') || ''
  } catch {
    return ''
  }
}
