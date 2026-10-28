CREATE TABLE IF NOT EXISTS quality_experiments (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(160) NOT NULL,
  experiment_type VARCHAR(64) NOT NULL DEFAULT 'Baseline',
  baseline_id VARCHAR(120) NULL,
  controlled_variable VARCHAR(160) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'Open',
  description TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_quality_experiment_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS quality_experiment_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  experiment_id BIGINT UNSIGNED NOT NULL,
  test_case VARCHAR(120) NOT NULL,
  task_id BIGINT UNSIGNED NULL,
  parent_task_id BIGINT UNSIGNED NULL,
  workflow_version VARCHAR(160) NULL,
  model_name VARCHAR(255) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'Recorded',
  parameters_json JSON NULL,
  metrics_json JSON NULL,
  human_rating TINYINT NULL,
  notes TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_quality_runs_experiment (experiment_id),
  KEY ix_quality_runs_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS quality_golden_samples (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  sample_key VARCHAR(160) NOT NULL,
  sample_type VARCHAR(64) NOT NULL,
  path VARCHAR(1024) NOT NULL,
  task_id BIGINT UNSIGNED NULL,
  quality_score DECIMAL(5,2) NULL,
  metadata_json JSON NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_quality_golden_key (sample_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS quality_repair_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  shot_id BIGINT UNSIGNED NULL,
  source_task_id BIGINT UNSIGNED NULL,
  retry_task_id BIGINT UNSIGNED NULL,
  issue_code VARCHAR(80) NOT NULL,
  strategy VARCHAR(160) NOT NULL,
  changed_parameters_json JSON NULL,
  result_status VARCHAR(32) NULL,
  metrics_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_quality_repairs_shot (shot_id),
  KEY ix_quality_repairs_task (retry_task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
