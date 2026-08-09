-- AI Video Studio 视频质量验收迁移
-- 只新增字段、表和默认预设，不删除或覆盖已有素材。

CREATE TABLE IF NOT EXISTS qa_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  episode_id BIGINT UNSIGNED NULL,
  shot_id BIGINT UNSIGNED NULL,
  qa_version INT NOT NULL DEFAULT 1,
  preset_name VARCHAR(32) NOT NULL DEFAULT 'Standard',
  run_type VARCHAR(32) NOT NULL DEFAULT 'Shot',
  mode VARCHAR(32) NOT NULL DEFAULT 'Auto',
  status VARCHAR(32) NOT NULL DEFAULT 'Running',
  score DECIMAL(5,2) NULL,
  issue_count INT NOT NULL DEFAULT 0,
  result_json JSON NULL,
  started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_qa_runs_episode_created (episode_id, created_at),
  KEY ix_qa_runs_shot_created (shot_id, created_at),
  CONSTRAINT fk_qa_runs_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
  CONSTRAINT fk_qa_runs_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS qa_issues (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  qa_run_id BIGINT UNSIGNED NULL,
  episode_id BIGINT UNSIGNED NULL,
  shot_id BIGINT UNSIGNED NULL,
  issue_type VARCHAR(64) NOT NULL,
  severity VARCHAR(16) NOT NULL DEFAULT 'Warning',
  description TEXT NOT NULL,
  frame_time DECIMAL(12,3) NULL,
  frame_path VARCHAR(1024) NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'Open',
  resolution_note TEXT NULL,
  resolved_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_qa_issues_episode_created (episode_id, created_at),
  KEY ix_qa_issues_shot_created (shot_id, created_at),
  KEY ix_qa_issues_severity_status (severity, status),
  CONSTRAINT fk_qa_issues_run FOREIGN KEY (qa_run_id) REFERENCES qa_runs(id) ON DELETE SET NULL,
  CONSTRAINT fk_qa_issues_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
  CONSTRAINT fk_qa_issues_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS qa_presets (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(32) NOT NULL,
  description VARCHAR(255) NULL,
  config_json JSON NOT NULL,
  shot_pass_score DECIMAL(5,2) NOT NULL DEFAULT 80,
  shot_review_score DECIMAL(5,2) NOT NULL DEFAULT 70,
  episode_pass_score DECIMAL(5,2) NOT NULL DEFAULT 85,
  black_frame_max_percent DECIMAL(5,2) NOT NULL DEFAULT 2,
  duration_tolerance_percent DECIMAL(5,2) NOT NULL DEFAULT 10,
  fps_tolerance DECIMAL(5,2) NOT NULL DEFAULT 1,
  max_auto_retries INT NOT NULL DEFAULT 2,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_qa_presets_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT IGNORE INTO qa_presets
  (name, description, config_json, shot_pass_score, shot_review_score, episode_pass_score, black_frame_max_percent, duration_tolerance_percent, fps_tolerance, max_auto_retries)
VALUES
  ('Draft', '快速预检，适合生成中间版本', '{"technical":true,"content":"manual","episode":true}', 70, 60, 75, 2, 10, 1, 2),
  ('Standard', '默认验收标准，适合 RTX 4070 12GB 短剧生产', '{"technical":true,"content":"cpu_ffmpeg_manual","episode":true}', 80, 70, 85, 2, 10, 1, 2),
  ('HighQuality', '高质量发布前验收', '{"technical":true,"content":"cpu_ffmpeg_manual","episode":true,"strict":true}', 88, 80, 88, 2, 10, 1, 2);
