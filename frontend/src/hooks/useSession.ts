import { useEffect } from 'react'
import { createSession } from '../api/client'
import { useChatStore } from '../stores/chatStore'

const SESSION_KEY_PREFIX = 'codingagent_session_id'

export function useSession() {
  const sessionId = useChatStore((s) => s.sessionId)
  const accessToken = useChatStore((s) => s.accessToken)
  const currentTenant = useChatStore((s) => s.currentTenant)
  const setSessionId = useChatStore((s) => s.setSessionId)

  useEffect(() => {
    if (!accessToken || !currentTenant) {
      setSessionId(null)
      return
    }

    const key = `${SESSION_KEY_PREFIX}:${currentTenant.tenant_id}`
    const stored = localStorage.getItem(key)
    if (stored) {
      setSessionId(stored)
      return
    }

    createSession('web_user', 'coding', accessToken)
      .then((res) => {
        localStorage.setItem(key, res.session_id)
        setSessionId(res.session_id)
      })
      .catch(console.error)
  }, [accessToken, currentTenant, setSessionId])

  return sessionId
}
