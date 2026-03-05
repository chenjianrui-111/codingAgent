import { useEffect, useState } from 'react'
import AcceptInvitationPage from './components/AcceptInvitationPage'
import AuthLoginPanel from './components/AuthLoginPanel'
import ChatPanel from './components/ChatPanel'
import DataAnalysisPanel from './components/DataAnalysisPanel'
import { useAuth } from './hooks/useAuth'
import { useSession } from './hooks/useSession'
import { useChatStore } from './stores/chatStore'

export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname)
  const {
    ready,
    loading,
    user,
    currentTenant,
    tenants,
    login,
    logout,
    switchCurrentTenant,
    inviteMember,
    fetchInvitations,
    acceptInvitationByCode,
  } = useAuth()
  const sessionId = useSession()
  const accessToken = useChatStore((s) => s.accessToken)

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = (path: string) => {
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path)
      setPathname(path)
    }
  }

  const openAcceptPage = () => navigate('/accept-invite')
  const openChatPage = () => navigate('/')
  const openDataPage = () => navigate('/data')

  if (!ready) {
    return (
      <div className="flex items-center justify-center h-screen text-gray-400 bg-gray-950">
        Initializing authentication...
      </div>
    )
  }

  if (!user || !currentTenant) {
    return (
      <AuthLoginPanel
        loading={loading}
        onLogin={async (idToken) => {
          await login(idToken)
        }}
      />
    )
  }

  if (pathname === '/accept-invite') {
    return (
      <AcceptInvitationPage
        authenticated={Boolean(user)}
        currentTenant={currentTenant}
        onBackToChat={openChatPage}
        onAccept={async (inviteCode) => {
          const resp = await acceptInvitationByCode(inviteCode)
          return resp.tenant
        }}
      />
    )
  }

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-screen text-gray-400 bg-gray-950">
        Initializing tenant session...
      </div>
    )
  }

  if (pathname === '/data') {
    return (
      <DataAnalysisPanel
        sessionId={sessionId}
        accessToken={accessToken || undefined}
        onBack={openChatPage}
      />
    )
  }

  return (
    <ChatPanel
      userEmail={user.email}
      currentTenant={currentTenant}
      tenants={tenants.length > 0 ? tenants : [currentTenant]}
      onSwitchTenant={switchCurrentTenant}
      onInvite={async (email, role, expiresInHours) => {
        const resp = await inviteMember(email, role, expiresInHours)
        return {
          inviteCode: resp.invitation.invite_code,
          inviteLink: resp.invite_link,
          emailSent: resp.email_sent,
          emailError: resp.email_error,
        }
      }}
      onLoadPendingInvites={async () => fetchInvitations('pending')}
      onOpenAcceptPage={openAcceptPage}
      onOpenDataPage={openDataPage}
      onLogout={logout}
    />
  )
}
