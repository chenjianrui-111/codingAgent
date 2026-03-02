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
