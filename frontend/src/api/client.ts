import type {
  AuthMeResponse,
  GoogleLoginResponse,
  TenantInvitationAcceptResponse,
  TenantInvitationListResponse,
  TenantInviteResponse,
  TenantListResponse,
  TenantSwitchResponse,
} from './types'

const API_BASE = '/api/v1'

function buildHeaders(accessToken?: string): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`
  }
  return headers
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text()
    throw new Error(body || `Request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export async function createSession(
  influencerName: string,
  category: string,
  accessToken?: string,
): Promise<{ session_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: buildHeaders(accessToken),
    body: JSON.stringify({ influencer_name: influencerName, category }),
  })
  return parseJson<{ session_id: string; status: string }>(res)
}

export async function agentStream(
  sessionId: string,
  query: string,
  currentFile?: string,
  workspace?: string,
  accessToken?: string,
): Promise<Response> {
  const body: Record<string, unknown> = { session_id: sessionId, query }
  if (currentFile) body.current_file = currentFile
  if (workspace) body.workspace = workspace

  const res = await fetch(`${API_BASE}/agent/stream`, {
    method: 'POST',
    headers: buildHeaders(accessToken),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Agent stream failed: ${res.status}`)
  return res
}

export async function googleLogin(
  idToken: string,
  tenantId?: string,
): Promise<GoogleLoginResponse> {
  const payload: Record<string, string> = { id_token: idToken }
  if (tenantId) payload.tenant_id = tenantId
  const res = await fetch(`${API_BASE}/auth/google/login`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  })
  return parseJson<GoogleLoginResponse>(res)
}

export async function authMe(accessToken: string): Promise<AuthMeResponse> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    method: 'GET',
    headers: buildHeaders(accessToken),
  })
  return parseJson<AuthMeResponse>(res)
}

export async function listTenants(accessToken: string): Promise<TenantListResponse> {
  const res = await fetch(`${API_BASE}/auth/tenants`, {
    method: 'GET',
    headers: buildHeaders(accessToken),
  })
  return parseJson<TenantListResponse>(res)
}

export async function switchTenant(
  accessToken: string,
  tenantId: string,
): Promise<TenantSwitchResponse> {
  const res = await fetch(`${API_BASE}/auth/tenant/switch`, {
    method: 'POST',
    headers: buildHeaders(accessToken),
    body: JSON.stringify({ tenant_id: tenantId }),
  })
  return parseJson<TenantSwitchResponse>(res)
}

export async function createTenantInvitation(
  accessToken: string,
  inviteeEmail: string,
  role: 'member' | 'admin',
  expiresInHours = 72,
): Promise<TenantInviteResponse> {
  const res = await fetch(`${API_BASE}/auth/tenant/invitations`, {
    method: 'POST',
    headers: buildHeaders(accessToken),
    body: JSON.stringify({
      invitee_email: inviteeEmail,
      role,
      expires_in_hours: expiresInHours,
    }),
  })
  return parseJson<TenantInviteResponse>(res)
}

export async function listTenantInvitations(
  accessToken: string,
  status = 'pending',
): Promise<TenantInvitationListResponse> {
  const res = await fetch(`${API_BASE}/auth/tenant/invitations?status=${encodeURIComponent(status)}`, {
    method: 'GET',
    headers: buildHeaders(accessToken),
  })
  return parseJson<TenantInvitationListResponse>(res)
}

export async function acceptTenantInvitation(
  accessToken: string,
  inviteCode: string,
): Promise<TenantInvitationAcceptResponse> {
  const res = await fetch(`${API_BASE}/auth/tenant/invitations/accept`, {
    method: 'POST',
    headers: buildHeaders(accessToken),
    body: JSON.stringify({ invite_code: inviteCode }),
  })
  return parseJson<TenantInvitationAcceptResponse>(res)
}
