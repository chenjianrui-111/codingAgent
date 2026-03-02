import { useState } from 'react'
import GoogleSignInButton from './GoogleSignInButton'

interface Props {
  loading: boolean
  onLogin: (idToken: string) => Promise<void>
}

export default function AuthLoginPanel({ loading, onLogin }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

  const handleLoginByCredential = async (idToken: string) => {
    setError(null)
    setSubmitting(true)
    try {
      await onLogin(idToken)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center px-4">
      <div className="w-full max-w-2xl rounded-2xl border border-gray-800 bg-gray-900 p-6 shadow-2xl">
        <h1 className="text-xl font-semibold">Sign In With Google</h1>
        <p className="text-sm text-gray-400 mt-1">Use your Google account to continue.</p>

        {!clientId && (
          <div className="mt-4 rounded-lg border border-amber-800 bg-amber-950/30 px-3 py-2 text-sm text-amber-200">
            Missing `VITE_GOOGLE_CLIENT_ID`. Add it to `frontend/.env.local` and restart the frontend.
          </div>
        )}

        <div className="mt-5 flex flex-col items-start gap-3">
          <GoogleSignInButton
            clientId={clientId}
            disabled={loading || submitting || !clientId}
            onCredential={(credential) => {
              void handleLoginByCredential(credential)
            }}
            onError={(msg) => setError(msg)}
          />
          {error && <p className="text-sm text-red-400">{error}</p>}
          {(loading || submitting) && <p className="text-sm text-gray-400">Signing in...</p>}
        </div>
      </div>
    </div>
  )
}
