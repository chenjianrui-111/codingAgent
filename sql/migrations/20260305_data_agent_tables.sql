-- Data Agent: Dataset management and analysis run tracking
-- Migration: 2026-03-05

-- Datasets table: uploaded/connected data sources for analysis
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id   VARCHAR(64)   PRIMARY KEY,
    session_id   VARCHAR(64)   NOT NULL,
    tenant_id    VARCHAR(64)   NULL,
    name         VARCHAR(256)  NOT NULL,
    file_path    VARCHAR(1024) NOT NULL,
    file_type    VARCHAR(32)   NOT NULL COMMENT 'csv / excel / json / parquet / sqlite',
    file_size_bytes INT        NOT NULL DEFAULT 0,
    row_count    INT           NOT NULL DEFAULT 0,
    column_count INT           NOT NULL DEFAULT 0,
    schema_json  TEXT          NULL     COMMENT 'JSON: column metadata array',
    summary_json TEXT          NULL     COMMENT 'JSON: descriptive statistics',
    sample_rows_json TEXT      NULL     COMMENT 'JSON: first N rows for preview',
    status       VARCHAR(32)   NOT NULL DEFAULT 'ready' COMMENT 'uploading / ready / error',
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_datasets_session (session_id),
    INDEX idx_datasets_tenant  (tenant_id),
    CONSTRAINT fk_datasets_session FOREIGN KEY (session_id) REFERENCES sessions(session_id)
) DEFAULT CHARSET=utf8mb4;

-- Dataset columns: per-column schema and statistics
CREATE TABLE IF NOT EXISTS dataset_columns (
    column_id    INT           PRIMARY KEY AUTO_INCREMENT,
    dataset_id   VARCHAR(64)   NOT NULL,
    column_name  VARCHAR(256)  NOT NULL,
    dtype        VARCHAR(64)   NOT NULL COMMENT 'int64 / float64 / object / datetime64 / bool',
    nullable     TINYINT(1)    NOT NULL DEFAULT 1,
    unique_count INT           NOT NULL DEFAULT 0,
    null_count   INT           NOT NULL DEFAULT 0,
    min_value    VARCHAR(256)  NULL,
    max_value    VARCHAR(256)  NULL,
    mean_value   VARCHAR(256)  NULL,
    sample_values_json TEXT    NULL COMMENT 'JSON: top sample values',
    INDEX idx_dscols_dataset (dataset_id),
    CONSTRAINT fk_dscols_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

-- Data analysis runs: each NL query -> code -> execution -> result
CREATE TABLE IF NOT EXISTS data_analysis_runs (
    analysis_id  VARCHAR(64)   PRIMARY KEY,
    dataset_id   VARCHAR(64)   NOT NULL,
    session_id   VARCHAR(64)   NOT NULL,
    query        TEXT          NOT NULL,
    generated_code TEXT        NULL,
    execution_stdout TEXT      NULL,
    execution_stderr TEXT      NULL,
    result_json  TEXT          NULL     COMMENT 'JSON: structured analysis result',
    visualization_paths_json TEXT NULL  COMMENT 'JSON: list of chart file paths',
    status       VARCHAR(32)   NOT NULL DEFAULT 'pending' COMMENT 'pending / running / completed / failed',
    error_message TEXT         NULL,
    execution_time_ms INT      NOT NULL DEFAULT 0,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_dar_dataset (dataset_id),
    INDEX idx_dar_session (session_id),
    CONSTRAINT fk_dar_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    CONSTRAINT fk_dar_session FOREIGN KEY (session_id) REFERENCES sessions(session_id)
) DEFAULT CHARSET=utf8mb4;
