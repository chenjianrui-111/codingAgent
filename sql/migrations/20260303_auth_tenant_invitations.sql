CREATE TABLE IF NOT EXISTS tenant_invitations (
  invitation_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  invite_code VARCHAR(96) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  invitee_email VARCHAR(256) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'member',
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  invited_by_user_id VARCHAR(64) NOT NULL,
  accepted_by_user_id VARCHAR(64) NULL,
  expires_at TIMESTAMP NOT NULL,
  accepted_at TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_invite_code (invite_code),
  INDEX idx_invite_tenant (tenant_id),
  INDEX idx_invite_email (invitee_email),
  INDEX idx_invite_status (status)
);
