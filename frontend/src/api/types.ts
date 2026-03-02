// Types aligned with backend schemas

export interface StreamEvent {
  type:
    | 'status'
    | 'text_delta'
    | 'tool_call'
    | 'tool_result'
    | 'diff_preview'
    | 'approval_required'
    | 'error'
    | 'done'
  data: Record<string, unknown>
}

export interface ChatMessage {
  id: string
  type: 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'diff_preview' | 'approval' | 'status'
  content: string
  timestamp: number
  // Tool-specific fields
  toolName?: string
  toolInput?: Record<string, unknown>
  toolId?: string
  success?: boolean
  // Diff-specific
  filePath?: string
  // Approval-specific
  runId?: string
  reason?: string
}

export interface Session {
  session_id: string
  status: string
}

export interface AuthUserInfo {
  user_id: string
  email: string
  display_name?: string | null
  avatar_url?: string | null
}

export interface AuthTenantInfo {
  tenant_id: string
  tenant_name: string
  tenant_slug: string
  role: string
}

export interface GoogleLoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  user: AuthUserInfo
  tenant: AuthTenantInfo
}

export interface AuthMeResponse {
  user: AuthUserInfo
  tenant: AuthTenantInfo
}

export interface TenantListResponse {
  current_tenant_id: string
  tenants: AuthTenantInfo[]
}

export interface TenantSwitchResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  tenant: AuthTenantInfo
}

export interface TenantInvitationItem {
  invitation_id: number
  invite_code: string
  invitee_email: string
  role: string
  status: string
  tenant_id: string
  invited_by_user_id: string
  accepted_by_user_id?: string | null
  expires_at: string
  created_at: string
  accepted_at?: string | null
}

export interface TenantInviteResponse {
  invitation: TenantInvitationItem
  tenant: AuthTenantInfo
  invite_link: string
  email_sent: boolean
  email_provider?: string | null
  email_message_id?: string | null
  email_error?: string | null
}

export interface TenantInvitationListResponse {
  invitations: TenantInvitationItem[]
}

export interface TenantInvitationAcceptResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  tenant: AuthTenantInfo
}
