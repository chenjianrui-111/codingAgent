import { useCallback, useEffect, useState } from 'react'
import {
  acceptTenantInvitation,
  authMe,
  createTenantInvitation,
  googleLogin,
  listTenantInvitations,
  listTenants,
  switchTenant,
} from '../api/client'
import type { AuthTenantInfo, TenantInvitationItem } from '../api/types'
import { useChatStore } from '../stores/chatStore'

const ACCESS_TOKEN_KEY = 'codingagent_access_token'

export function useAuth() {
  const accessToken = useChatStore((s) => s.accessToken)
  const user = useChatStore((s) => s.user)
  const currentTenant = useChatStore((s) => s.currentTenant)
  const tenants = useChatStore((s) => s.tenants)
  const setAuthContext = useChatStore((s) => s.setAuthContext)
  const setCurrentTenant = useChatStore((s) => s.setCurrentTenant)
  const setTenants = useChatStore((s) => s.setTenants)
  const clearAuth = useChatStore((s) => s.clearAuth)

  const [ready, setReady] = useState(false)
  const [loading, setLoading] = useState(false)

  const syncTenantList = useCallback(
    async (token: string): Promise<AuthTenantInfo[]> => {
      const list = await listTenants(token)
      setTenants(list.tenants)
      return list.tenants
    },
    [setTenants],
  )

  useEffect(() => {
    const storedToken = localStorage.getItem(ACCESS_TOKEN_KEY)
    if (!storedToken) {
      setReady(true)
      return
    }

    let mounted = true
    setLoading(true)
    authMe(storedToken)
      .then(async (me) => {
        if (!mounted) return
        setAuthContext(storedToken, me.user, me.tenant)
        await syncTenantList(storedToken)
      })
      .catch(() => {
        if (!mounted) return
        localStorage.removeItem(ACCESS_TOKEN_KEY)
        clearAuth()
      })
      .finally(() => {
        if (!mounted) return
        setLoading(false)
        setReady(true)
      })

    return () => {
      mounted = false
    }
  }, [clearAuth, setAuthContext, syncTenantList])

  const login = useCallback(
    async (idToken: string) => {
      const resp = await googleLogin(idToken)
      localStorage.setItem(ACCESS_TOKEN_KEY, resp.access_token)
      setAuthContext(resp.access_token, resp.user, resp.tenant)
      await syncTenantList(resp.access_token)
      return resp
    },
    [setAuthContext, syncTenantList],
  )

  const logout = useCallback(() => {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    clearAuth()
  }, [clearAuth])

  const switchCurrentTenant = useCallback(
    async (tenantId: string) => {
      if (!accessToken) throw new Error('Not authenticated')
      const resp = await switchTenant(accessToken, tenantId)
      localStorage.setItem(ACCESS_TOKEN_KEY, resp.access_token)
      setCurrentTenant(resp.access_token, resp.tenant)
      await syncTenantList(resp.access_token)
      return resp
    },
    [accessToken, setCurrentTenant, syncTenantList],
  )

  const inviteMember = useCallback(
    async (inviteeEmail: string, role: 'member' | 'admin', expiresInHours: number) => {
      if (!accessToken) throw new Error('Not authenticated')
      return createTenantInvitation(accessToken, inviteeEmail, role, expiresInHours)
    },
    [accessToken],
  )

  const fetchInvitations = useCallback(
    async (status = 'pending'): Promise<TenantInvitationItem[]> => {
      if (!accessToken) throw new Error('Not authenticated')
      const resp = await listTenantInvitations(accessToken, status)
      return resp.invitations
    },
    [accessToken],
  )

  const acceptInvitationByCode = useCallback(
    async (inviteCode: string) => {
      if (!accessToken) throw new Error('Not authenticated')
      const resp = await acceptTenantInvitation(accessToken, inviteCode)
      localStorage.setItem(ACCESS_TOKEN_KEY, resp.access_token)
      const me = await authMe(resp.access_token)
      setAuthContext(resp.access_token, me.user, me.tenant)
      await syncTenantList(resp.access_token)
      return resp
    },
    [accessToken, setAuthContext, syncTenantList],
  )

  return {
    ready,
    loading,
    accessToken,
    user,
    currentTenant,
    tenants,
    login,
    logout,
    switchCurrentTenant,
    inviteMember,
    fetchInvitations,
    acceptInvitationByCode,
  }
}
