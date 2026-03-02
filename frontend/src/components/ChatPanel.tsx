import { useState, useRef, useEffect } from 'react'
import { useChatStore } from '../stores/chatStore'
import { useAgentStream } from '../hooks/useAgentStream'
import type { AuthTenantInfo, TenantInvitationItem } from '../api/types'
import MessageBubble from './MessageBubble'
import ToolCallCard from './ToolCallCard'
import DiffPreview from './DiffPreview'
import ApprovalDialog from './ApprovalDialog'
import StatusIndicator from './StatusIndicator'
import InviteMemberModal from './InviteMemberModal'

interface Props {
  userEmail: string
  currentTenant: AuthTenantInfo
  tenants: AuthTenantInfo[]
  onSwitchTenant: (tenantId: string) => Promise<unknown>
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
  onLoadPendingInvites: () => Promise<TenantInvitationItem[]>
  onOpenAcceptPage: () => void
  onLogout: () => void
}

export default function ChatPanel({
  userEmail,
  currentTenant,
  tenants,
  onSwitchTenant,
  onInvite,
  onLoadPendingInvites,
  onOpenAcceptPage,
  onLogout,
}: Props) {
  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const currentStatus = useChatStore((s) => s.currentStatus)
  const { sendMessage } = useAgentStream()

  const [input, setInput] = useState('')
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentStatus])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || isStreaming) return
    setInput('')
    sendMessage(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleSwitchTenant = async (tenantId: string) => {
    if (tenantId === currentTenant.tenant_id || actionLoading) return
    setActionLoading(true)
    try {
      await onSwitchTenant(tenantId)
    } catch (err) {
      useChatStore.getState().addMessage({
        type: 'status',
        content: `Switch tenant failed: ${err instanceof Error ? err.message : String(err)}`,
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleInvite = async (email: string, role: 'member' | 'admin', expiresInHours: number) => {
    const result = await onInvite(email, role, expiresInHours)
    useChatStore.getState().addMessage({
      type: 'status',
      content:
        `Invitation created for ${email}: ${result.inviteCode}` +
        (result.emailSent ? ' (email sent)' : ` (email not sent: ${result.emailError || 'disabled'})`),
    })
    return result
  }

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-gray-800 gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-sm font-bold">
            C
          </div>
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-gray-100">Coding Agent</h1>
            <p className="text-xs text-gray-500 truncate">
              {userEmail} · {currentTenant.tenant_name} ({currentTenant.role})
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={currentTenant.tenant_id}
            onChange={(e) => void handleSwitchTenant(e.target.value)}
            disabled={actionLoading}
            className="max-w-[220px] rounded-lg border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-200"
          >
            {tenants.map((tenant) => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.tenant_name} ({tenant.role})
              </option>
            ))}
          </select>
          <button
            onClick={() => setInviteModalOpen(true)}
            type="button"
            className="rounded-lg border border-blue-700 px-2 py-1 text-xs text-blue-200 hover:bg-blue-900/40"
          >
            Invite
          </button>
          <button
            onClick={onOpenAcceptPage}
            type="button"
            className="rounded-lg border border-emerald-700 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-900/40"
          >
            Accept Invite
          </button>
          <button
            onClick={onLogout}
            type="button"
            className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:bg-gray-800"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto py-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <div className="text-4xl mb-4">&#128187;</div>
            <p className="text-lg mb-1">What can I help you build?</p>
            <p className="text-sm">Describe a coding task and I'll get to work.</p>
          </div>
        )}

        {messages.map((msg) => {
          switch (msg.type) {
            case 'user':
            case 'assistant':
            case 'status':
              return <MessageBubble key={msg.id} message={msg} />
            case 'tool_call':
            case 'tool_result':
              return <ToolCallCard key={msg.id} message={msg} />
            case 'diff_preview':
              return <DiffPreview key={msg.id} message={msg} />
            case 'approval':
              return <ApprovalDialog key={msg.id} message={msg} />
            default:
              return null
          }
        })}

        {isStreaming && currentStatus && <StatusIndicator status={currentStatus} />}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="px-4 py-3 border-t border-gray-800">
        <div className="flex items-end gap-2 bg-gray-900 rounded-xl border border-gray-700 focus-within:border-blue-600 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe a coding task..."
            rows={1}
            className="flex-1 bg-transparent px-4 py-3 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none"
            style={{ maxHeight: '120px' }}
            disabled={isStreaming}
          />
          <button
            type="submit"
            disabled={isStreaming || !input.trim()}
            className="px-4 py-3 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed rounded-r-xl transition-colors"
          >
            {isStreaming ? '...' : 'Send'}
          </button>
        </div>
      </form>

      <InviteMemberModal
        open={inviteModalOpen}
        loading={actionLoading}
        onClose={() => setInviteModalOpen(false)}
        onInvite={handleInvite}
        onLoadPending={onLoadPendingInvites}
      />
    </div>
  )
}
