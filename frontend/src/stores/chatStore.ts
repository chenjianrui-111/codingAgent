import { create } from 'zustand'
import type { AuthTenantInfo, AuthUserInfo, ChatMessage } from '../api/types'

let _nextId = 0
function nextId(): string {
  return `msg_${++_nextId}_${Date.now()}`
}

interface ChatState {
  messages: ChatMessage[]
  isStreaming: boolean
  sessionId: string | null
  currentStatus: string | null
  accessToken: string | null
  user: AuthUserInfo | null
  currentTenant: AuthTenantInfo | null
  tenants: AuthTenantInfo[]

  setSessionId: (id: string | null) => void
  setStreaming: (v: boolean) => void
  setStatus: (status: string | null) => void
  setAuthContext: (accessToken: string, user: AuthUserInfo, tenant: AuthTenantInfo) => void
  setCurrentTenant: (accessToken: string, tenant: AuthTenantInfo) => void
  setTenants: (tenants: AuthTenantInfo[]) => void
  clearAuth: () => void
  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => void
  appendToLastAssistant: (text: string) => void
  updateToolResult: (toolId: string, success: boolean, output: string) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isStreaming: false,
  sessionId: null,
  currentStatus: null,
  accessToken: null,
  user: null,
  currentTenant: null,
  tenants: [],

  setSessionId: (id) => set({ sessionId: id }),
  setStreaming: (v) => set({ isStreaming: v }),
  setStatus: (status) => set({ currentStatus: status }),
  setAuthContext: (accessToken, user, tenant) =>
    set((state) => ({
      accessToken,
      user,
      currentTenant: tenant,
      tenants: upsertTenant(state.tenants, tenant),
      sessionId: null,
    })),
  setCurrentTenant: (accessToken, tenant) =>
    set((state) => ({
      accessToken,
      currentTenant: tenant,
      tenants: upsertTenant(state.tenants, tenant),
      sessionId: null,
    })),
  setTenants: (tenants) => set({ tenants }),
  clearAuth: () =>
    set({
      accessToken: null,
      user: null,
      currentTenant: null,
      tenants: [],
      sessionId: null,
    }),

  addMessage: (msg) =>
    set((state) => ({
      messages: [
        ...state.messages,
        { ...msg, id: nextId(), timestamp: Date.now() },
      ],
    })),

  appendToLastAssistant: (text) =>
    set((state) => {
      const msgs = [...state.messages]
      const lastIdx = msgs.length - 1
      if (lastIdx >= 0 && msgs[lastIdx].type === 'assistant') {
        msgs[lastIdx] = { ...msgs[lastIdx], content: msgs[lastIdx].content + text }
      } else {
        msgs.push({
          id: nextId(),
          type: 'assistant',
          content: text,
          timestamp: Date.now(),
        })
      }
      return { messages: msgs }
    }),

  updateToolResult: (toolId, success, output) =>
    set((state) => {
      const msgs = state.messages.map((m) =>
        m.toolId === toolId
          ? { ...m, type: 'tool_result' as const, success, content: output }
          : m,
      )
      return { messages: msgs }
    }),

  clearMessages: () => set({ messages: [] }),
}))

function upsertTenant(existing: AuthTenantInfo[], tenant: AuthTenantInfo): AuthTenantInfo[] {
  const found = existing.find((x) => x.tenant_id === tenant.tenant_id)
  if (!found) return [...existing, tenant]
  return existing.map((x) => (x.tenant_id === tenant.tenant_id ? tenant : x))
}
