-- OceanBase MySQL mode bootstrap script for coding-agent MVP
-- Execute with tenant user that has CREATE DATABASE / CREATE TABLE privileges.

CREATE DATABASE IF NOT EXISTS coding_agent DEFAULT CHARACTER SET utf8mb4;
USE coding_agent;

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

CREATE TABLE IF NOT EXISTS sessions (
  session_id VARCHAR(64) PRIMARY KEY,
  influencer_name VARCHAR(128) NOT NULL,
  category VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NULL,
  owner_user_id VARCHAR(64) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_session_tenant (tenant_id),
  INDEX idx_session_owner (owner_user_id)
);

CREATE TABLE IF NOT EXISTS requirements (
  requirement_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(64) NOT NULL,
  query_text TEXT NOT NULL,
  priority VARCHAR(32) NOT NULL DEFAULT 'medium',
  estimated_points INT NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL DEFAULT 'created',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_req_session (session_id)
);

CREATE TABLE IF NOT EXISTS tasks (
  task_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  requirement_id BIGINT NOT NULL,
  role VARCHAR(32) NOT NULL,
  instruction TEXT NOT NULL,
  output_text LONGTEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_req (requirement_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
  call_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(64) NOT NULL,
  tool_name VARCHAR(64) NOT NULL,
  request_text LONGTEXT NOT NULL,
  response_text LONGTEXT NOT NULL,
  latency_ms INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_call_session (session_id)
);

CREATE TABLE IF NOT EXISTS repo_files (
  file_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  file_path VARCHAR(1024) NOT NULL,
  file_sha VARCHAR(128) NOT NULL,
  language VARCHAR(32) NOT NULL,
  content LONGTEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_repo_branch_path (repo_name, branch_name, file_path)
);

CREATE TABLE IF NOT EXISTS code_chunks (
  chunk_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  file_path VARCHAR(1024) NOT NULL,
  chunk_text LONGTEXT NOT NULL,
  start_line INT NOT NULL,
  end_line INT NOT NULL,
  embedding VECTOR(1536),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_chunk_file (repo_name, branch_name, file_path)
);

CREATE TABLE IF NOT EXISTS eval_runs (
  eval_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(64) NOT NULL,
  task_name VARCHAR(256) NOT NULL,
  passed TINYINT NOT NULL,
  score DECIMAL(6, 2) NOT NULL DEFAULT 0,
  notes LONGTEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_eval_session (session_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
  event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  actor VARCHAR(128) NOT NULL,
  action VARCHAR(128) NOT NULL,
  resource_type VARCHAR(64) NOT NULL,
  resource_id VARCHAR(128) NOT NULL,
  payload LONGTEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_audit_actor_time (actor, created_at)
);

CREATE TABLE IF NOT EXISTS project_files (
  file_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  file_path VARCHAR(1024) NOT NULL,
  file_type VARCHAR(32) NOT NULL,
  file_size INT NOT NULL DEFAULT 0,
  depth INT NOT NULL DEFAULT 0,
  content_hash VARCHAR(128) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_project_file (repo_name, branch_name, file_path),
  INDEX idx_project_repo_branch (repo_name, branch_name)
);

CREATE TABLE IF NOT EXISTS code_symbols (
  symbol_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  file_path VARCHAR(1024) NOT NULL,
  symbol_name VARCHAR(256) NOT NULL,
  symbol_type VARCHAR(32) NOT NULL,
  start_line INT NOT NULL DEFAULT 1,
  end_line INT NOT NULL DEFAULT 1,
  signature VARCHAR(512) NULL,
  docstring LONGTEXT NULL,
  metadata_json LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_symbol_lookup (repo_name, branch_name, symbol_name),
  INDEX idx_symbol_file (repo_name, branch_name, file_path)
);

CREATE TABLE IF NOT EXISTS dependency_edges (
  edge_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  source_file VARCHAR(1024) NOT NULL,
  target_module VARCHAR(512) NOT NULL,
  edge_type VARCHAR(32) NOT NULL DEFAULT 'import',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_dep_source (repo_name, branch_name, source_file),
  INDEX idx_dep_target (repo_name, branch_name, target_module)
);

CREATE TABLE IF NOT EXISTS interaction_memories (
  memory_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(64) NOT NULL,
  role VARCHAR(32) NOT NULL,
  content LONGTEXT NOT NULL,
  content_hash VARCHAR(64) NOT NULL,
  importance_score INT NOT NULL DEFAULT 1,
  is_pinned TINYINT(1) NOT NULL DEFAULT 0,
  tags VARCHAR(256) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_memory_session_time (session_id, created_at),
  INDEX idx_memory_hash (session_id, content_hash)
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  chunk_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  source_type VARCHAR(32) NOT NULL DEFAULT 'code',
  source_path VARCHAR(1024) NOT NULL,
  start_line INT NOT NULL DEFAULT 1,
  end_line INT NOT NULL DEFAULT 1,
  chunk_text LONGTEXT NOT NULL,
  keywords VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_knowledge_source (repo_name, branch_name, source_path)
);

CREATE TABLE IF NOT EXISTS project_graph_nodes (
  node_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  node_key VARCHAR(1024) NOT NULL,
  node_type VARCHAR(32) NOT NULL,
  name VARCHAR(256) NOT NULL,
  file_path VARCHAR(1024) NULL,
  metadata_json LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_graph_node (repo_name, branch_name, node_key),
  INDEX idx_graph_node_type (repo_name, branch_name, node_type),
  INDEX idx_graph_node_file (repo_name, branch_name, file_path)
);

CREATE TABLE IF NOT EXISTS project_graph_edges (
  edge_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  source_key VARCHAR(1024) NOT NULL,
  target_key VARCHAR(1024) NOT NULL,
  edge_type VARCHAR(32) NOT NULL,
  weight INT NOT NULL DEFAULT 1,
  metadata_json LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_graph_edge_source (repo_name, branch_name, source_key),
  INDEX idx_graph_edge_target (repo_name, branch_name, target_key),
  INDEX idx_graph_edge_type (repo_name, branch_name, edge_type)
);

CREATE TABLE IF NOT EXISTS project_vectors (
  vector_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  repo_name VARCHAR(128) NOT NULL,
  branch_name VARCHAR(64) NOT NULL,
  entity_key VARCHAR(1024) NOT NULL,
  entity_type VARCHAR(32) NOT NULL,
  file_path VARCHAR(1024) NULL,
  text_content LONGTEXT NOT NULL,
  embedding_json LONGTEXT NOT NULL,
  keywords VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_project_vector (repo_name, branch_name, entity_key),
  INDEX idx_project_vector_type (repo_name, branch_name, entity_type),
  INDEX idx_project_vector_file (repo_name, branch_name, file_path)
);

CREATE TABLE IF NOT EXISTS agent_runs (
  run_id VARCHAR(64) PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL,
  requirement_id BIGINT NOT NULL,
  original_query LONGTEXT NOT NULL,
  interpreted_query LONGTEXT NOT NULL,
  persona_name VARCHAR(64) NOT NULL DEFAULT 'coding_deep_agent',
  complexity VARCHAR(16) NOT NULL DEFAULT 'simple',
  status VARCHAR(32) NOT NULL DEFAULT 'running',
  max_steps INT NOT NULL DEFAULT 12,
  current_step INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP NULL,
  INDEX idx_agent_run_session (session_id),
  INDEX idx_agent_run_requirement (requirement_id),
  INDEX idx_agent_run_status (status)
);

CREATE TABLE IF NOT EXISTS agent_todos (
  todo_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id VARCHAR(64) NOT NULL,
  parent_todo_id BIGINT NULL,
  role VARCHAR(32) NOT NULL,
  title VARCHAR(256) NOT NULL,
  instruction LONGTEXT NOT NULL,
  success_criteria VARCHAR(512) NOT NULL,
  depends_on_json LONGTEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  attempt_count INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 2,
  output_text LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_agent_todo_run (run_id),
  INDEX idx_agent_todo_parent (parent_todo_id),
  INDEX idx_agent_todo_status (run_id, status)
);

CREATE TABLE IF NOT EXISTS task_evaluations (
  evaluation_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id VARCHAR(64) NOT NULL,
  todo_id BIGINT NOT NULL,
  evaluator VARCHAR(32) NOT NULL DEFAULT 'rule_evaluator',
  passed TINYINT(1) NOT NULL DEFAULT 0,
  score INT NOT NULL DEFAULT 0,
  reason LONGTEXT NOT NULL,
  next_action VARCHAR(64) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_eval_run (run_id),
  INDEX idx_eval_todo (todo_id)
);

CREATE TABLE IF NOT EXISTS approval_events (
  event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id VARCHAR(64) NOT NULL,
  todo_id BIGINT NULL,
  gate_type VARCHAR(64) NOT NULL DEFAULT 'manual_gate',
  decision VARCHAR(32) NOT NULL DEFAULT 'pending',
  operator VARCHAR(128) NOT NULL DEFAULT 'system',
  comment LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_approval_run (run_id),
  INDEX idx_approval_todo (todo_id),
  INDEX idx_approval_gate (run_id, gate_type, decision)
);

CREATE TABLE IF NOT EXISTS agent_file_changes (
  change_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id VARCHAR(64) NOT NULL,
  file_path VARCHAR(1024) NOT NULL,
  change_type VARCHAR(16) NOT NULL COMMENT 'create / edit / delete',
  old_content LONGTEXT NULL,
  new_content LONGTEXT NOT NULL,
  diff_text LONGTEXT NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending / applied / rejected',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_file_change_run (run_id),
  INDEX idx_file_change_status (run_id, status)
);
