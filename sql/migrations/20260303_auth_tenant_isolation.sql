CREATE TABLE IF NOT EXISTS tenants (
  tenant_id VARCHAR(64) PRIMARY KEY,
  tenant_name VARCHAR(128) NOT NULL,
  tenant_slug VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tenant_slug (tenant_slug)
);

CREATE TABLE IF NOT EXISTS users (
  user_id VARCHAR(64) PRIMARY KEY,
  email VARCHAR(256) NOT NULL,
  display_name VARCHAR(128) NULL,
  avatar_url VARCHAR(512) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_email (email)
);

CREATE TABLE IF NOT EXISTS tenant_members (
  member_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  tenant_id VARCHAR(64) NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'member',
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_tenant_member (tenant_id, user_id),
  INDEX idx_member_tenant (tenant_id),
  INDEX idx_member_user (user_id)
);

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

CREATE TABLE IF NOT EXISTS google_identities (
  identity_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id VARCHAR(64) NOT NULL,
  google_sub VARCHAR(128) NOT NULL,
  email VARCHAR(256) NOT NULL,
  email_verified TINYINT(1) NOT NULL DEFAULT 0,
  raw_profile_json LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_google_sub (google_sub),
  INDEX idx_google_user (user_id)
);

CREATE TABLE IF NOT EXISTS auth_tokens (
  token_id VARCHAR(64) PRIMARY KEY,
  access_token VARCHAR(256) NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'member',
  expires_at TIMESTAMP NOT NULL,
  revoked TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_access_token (access_token),
  INDEX idx_token_user (user_id),
  INDEX idx_token_tenant (tenant_id),
  INDEX idx_token_expires (expires_at)
);

ALTER TABLE sessions ADD COLUMN tenant_id VARCHAR(64) NULL;
ALTER TABLE sessions ADD COLUMN owner_user_id VARCHAR(64) NULL;
CREATE INDEX idx_session_tenant ON sessions (tenant_id);
CREATE INDEX idx_session_owner ON sessions (owner_user_id);
