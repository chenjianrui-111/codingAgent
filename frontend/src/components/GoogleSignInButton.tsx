import { useEffect, useRef, useState } from 'react'

interface Props {
  clientId: string
  disabled?: boolean
  onCredential: (idToken: string) => void
  onError?: (message: string) => void
}

const GIS_SCRIPT_ID = 'google-identity-services'
const GIS_SRC = 'https://accounts.google.com/gsi/client'

export default function GoogleSignInButton({ clientId, disabled, onCredential, onError }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true

    if (!clientId.trim()) {
      setLoading(false)
      return
    }

    loadGisScript()
      .then(() => {
        if (!active) return
        if (!window.google?.accounts?.id) {
          onError?.('Google Identity Services is unavailable in this browser.')
          setLoading(false)
          return
        }

        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (resp) => {
            if (!resp.credential) {
              onError?.('Google did not return credential token.')
              return
            }
            onCredential(resp.credential)
          },
        })

        if (containerRef.current) {
          containerRef.current.innerHTML = ''
          window.google.accounts.id.renderButton(containerRef.current, {
            theme: 'outline',
            size: 'large',
            text: 'continue_with',
            shape: 'pill',
            logo_alignment: 'left',
            width: 320,
          })
        }

        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        onError?.(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })

    return () => {
      active = false
    }
  }, [clientId, onCredential, onError])

  return (
    <div className={disabled ? 'pointer-events-none opacity-60' : ''}>
      <div ref={containerRef} />
      {loading && <p className="text-xs text-gray-500 mt-2">Loading Google Sign-In...</p>}
    </div>
  )
}

function loadGisScript(): Promise<void> {
  const existing = document.getElementById(GIS_SCRIPT_ID) as HTMLScriptElement | null
  if (existing) {
    if ((existing as HTMLScriptElement).dataset.loaded === 'true') {
      return Promise.resolve()
    }
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => resolve(), { once: true })
      existing.addEventListener('error', () => reject(new Error('Failed to load GIS script')), { once: true })
    })
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.id = GIS_SCRIPT_ID
    script.src = GIS_SRC
    script.async = true
    script.defer = true
    script.onload = () => {
      script.dataset.loaded = 'true'
      resolve()
    }
    script.onerror = () => reject(new Error('Failed to load GIS script'))
    document.head.appendChild(script)
  })
}
