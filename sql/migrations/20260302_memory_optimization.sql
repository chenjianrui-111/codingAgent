-- Incremental migration for memory management optimization
-- Apply to existing coding_agent database if interaction_memories table already exists.

USE coding_agent;

ALTER TABLE interaction_memories
  ADD COLUMN content_hash VARCHAR(64) NOT NULL DEFAULT '';

ALTER TABLE interaction_memories
  ADD COLUMN importance_score INT NOT NULL DEFAULT 1;

ALTER TABLE interaction_memories
  ADD COLUMN is_pinned TINYINT(1) NOT NULL DEFAULT 0;

CREATE INDEX idx_memory_hash ON interaction_memories (session_id, content_hash);
