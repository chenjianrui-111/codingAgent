-- Incremental migration for project-level graph + vector context.
USE coding_agent;

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
