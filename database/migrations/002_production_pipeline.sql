-- AI Video Studio 第二阶段生产流水线迁移（MySQL 8.0.22+）
--
-- 这份文件是可审计的迁移记录。启动时由 ProductionSchemaMigrator 按 information_schema
-- 检查缺失列并安全执行；这样兼容现有 8.0.22，不删除任何已有用户数据。

ALTER TABLE projects
  ADD COLUMN aspect_ratio VARCHAR(8) NOT NULL DEFAULT '16:9',
  ADD COLUMN style VARCHAR(160) NULL,
  ADD COLUMN default_model_id BIGINT UNSIGNED NULL,
  ADD COLUMN default_workflow_id BIGINT UNSIGNED NULL,
  ADD COLUMN default_fps INT NOT NULL DEFAULT 30,
  ADD COLUMN default_width INT NOT NULL DEFAULT 1920,
  ADD COLUMN default_height INT NOT NULL DEFAULT 1080,
  ADD COLUMN prompt_style VARCHAR(255) NULL,
  ADD COLUMN bgm_path VARCHAR(1024) NULL,
  ADD COLUMN bgm_volume DECIMAL(5,2) NOT NULL DEFAULT 0.18;

ALTER TABLE characters
  ADD COLUMN voice_id VARCHAR(120) NULL,
  ADD COLUMN voice_speed DECIMAL(5,2) NOT NULL DEFAULT 1.00,
  ADD COLUMN voice_pitch DECIMAL(5,2) NOT NULL DEFAULT 0.00;

ALTER TABLE scenes
  ADD COLUMN lighting VARCHAR(160) NULL,
  ADD COLUMN time_of_day VARCHAR(80) NULL,
  ADD COLUMN weather VARCHAR(80) NULL,
  ADD COLUMN architecture TEXT NULL;

ALTER TABLE episodes
  ADD COLUMN script_id BIGINT UNSIGNED NULL,
  ADD COLUMN production_mode VARCHAR(32) NOT NULL DEFAULT 'ManualReview',
  ADD COLUMN narrator_voice_id VARCHAR(120) NULL,
  ADD COLUMN voice_volume DECIMAL(5,2) NOT NULL DEFAULT 1.00,
  ADD COLUMN bgm_volume DECIMAL(5,2) NOT NULL DEFAULT 0.18,
  ADD COLUMN sfx_volume DECIMAL(5,2) NOT NULL DEFAULT 0.60,
  ADD COLUMN subtitle_path VARCHAR(1024) NULL,
  ADD COLUMN cover_path VARCHAR(1024) NULL,
  ADD COLUMN total_duration_seconds DECIMAL(12,3) NULL;

ALTER TABLE shots
  ADD COLUMN action TEXT NULL,
  ADD COLUMN dialogue TEXT NULL,
  ADD COLUMN narration TEXT NULL,
  ADD COLUMN emotion VARCHAR(160) NULL,
  ADD COLUMN camera_type VARCHAR(120) NULL,
  ADD COLUMN camera_motion VARCHAR(160) NULL,
  ADD COLUMN duration_seconds DECIMAL(8,3) NOT NULL DEFAULT 5.00,
  ADD COLUMN character_prompt TEXT NULL,
  ADD COLUMN scene_prompt TEXT NULL,
  ADD COLUMN action_prompt TEXT NULL,
  ADD COLUMN camera_prompt TEXT NULL,
  ADD COLUMN lighting_prompt TEXT NULL,
  ADD COLUMN style_prompt TEXT NULL,
  ADD COLUMN quality_prompt TEXT NULL,
  ADD COLUMN prompt_version INT NOT NULL DEFAULT 1,
  ADD COLUMN prompt_locked TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN prompt_source_language VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
  ADD COLUMN selected_keyframe_path VARCHAR(1024) NULL,
  ADD COLUMN video_path VARCHAR(1024) NULL,
  ADD COLUMN final_video_path VARCHAR(1024) NULL,
  ADD COLUMN quality_score DECIMAL(5,2) NULL,
  ADD COLUMN user_rating TINYINT NULL,
  ADD COLUMN video_qc_json JSON NULL,
  ADD COLUMN audio_status VARCHAR(32) NOT NULL DEFAULT 'Pending',
  ADD COLUMN subtitle_status VARCHAR(32) NOT NULL DEFAULT 'Pending',
  ADD COLUMN generation_profile_json JSON NULL;

ALTER TABLE generation_tasks
  ADD COLUMN error_type VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
  ADD COLUMN resource_class VARCHAR(16) NOT NULL DEFAULT 'GPU',
  ADD COLUMN stage VARCHAR(64) NULL,
  ADD COLUMN dependency_task_id BIGINT UNSIGNED NULL,
  ADD COLUMN paused TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE generation_results
  ADD COLUMN candidate_index INT NULL,
  ADD COLUMN is_selected TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN quality_score DECIMAL(5,2) NULL,
  ADD COLUMN user_rating TINYINT NULL,
  ADD COLUMN qc_json JSON NULL,
  ADD COLUMN prompt_version INT NULL,
  ADD COLUMN seed BIGINT NULL;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version VARCHAR(64) NOT NULL,
  applied_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS scripts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  episode_id BIGINT UNSIGNED NULL,
  title VARCHAR(255) NOT NULL,
  content LONGTEXT NOT NULL,
  version INT NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL DEFAULT 'Draft',
  language VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
  analysis_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_scripts_project_updated (project_id, updated_at),
  CONSTRAINT fk_scripts_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  CONSTRAINT fk_scripts_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS script_versions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  script_id BIGINT UNSIGNED NOT NULL,
  version INT NOT NULL,
  title VARCHAR(255) NOT NULL,
  content LONGTEXT NOT NULL,
  analysis_json JSON NULL,
  change_note VARCHAR(500) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_script_versions (script_id, version),
  CONSTRAINT fk_script_versions_script FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS prompt_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  shot_id BIGINT UNSIGNED NOT NULL,
  version INT NOT NULL,
  prompt TEXT NULL,
  negative_prompt TEXT NULL,
  components_json JSON NULL,
  source VARCHAR(32) NOT NULL DEFAULT 'system',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_prompt_history_shot_version (shot_id, version),
  CONSTRAINT fk_prompt_history_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS shot_candidates (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  shot_id BIGINT UNSIGNED NOT NULL,
  task_id BIGINT UNSIGNED NULL,
  path VARCHAR(1024) NOT NULL,
  candidate_index INT NOT NULL DEFAULT 1,
  is_selected TINYINT(1) NOT NULL DEFAULT 0,
  qc_status VARCHAR(32) NOT NULL DEFAULT 'Pending',
  quality_score DECIMAL(5,2) NULL,
  qc_json JSON NULL,
  seed BIGINT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_shot_candidates_shot_created (shot_id, created_at),
  CONSTRAINT fk_shot_candidates_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE CASCADE,
  CONSTRAINT fk_shot_candidates_task FOREIGN KEY (task_id) REFERENCES generation_tasks(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS task_dependencies (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id BIGINT UNSIGNED NOT NULL,
  depends_on_task_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_dependency (task_id, depends_on_task_id),
  CONSTRAINT fk_task_dependencies_task FOREIGN KEY (task_id) REFERENCES generation_tasks(id) ON DELETE CASCADE,
  CONSTRAINT fk_task_dependencies_parent FOREIGN KEY (depends_on_task_id) REFERENCES generation_tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS audio_cache (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  cache_key CHAR(64) NOT NULL,
  text_content TEXT NOT NULL,
  voice_id VARCHAR(120) NOT NULL,
  speed DECIMAL(5,2) NOT NULL DEFAULT 1.00,
  pitch DECIMAL(5,2) NOT NULL DEFAULT 0.00,
  path VARCHAR(1024) NOT NULL,
  duration_seconds DECIMAL(12,4) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_audio_cache_key (cache_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS sound_effects (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  category VARCHAR(64) NOT NULL,
  path VARCHAR(1024) NOT NULL,
  sha256 CHAR(64) NULL,
  duration_seconds DECIMAL(12,4) NULL,
  volume DECIMAL(5,2) NOT NULL DEFAULT 0.60,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_sound_effect_path (path(768)),
  KEY ix_sound_effects_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS shot_sound_effects (
  shot_id BIGINT UNSIGNED NOT NULL,
  sound_effect_id BIGINT UNSIGNED NOT NULL,
  start_seconds DECIMAL(8,3) NOT NULL DEFAULT 0,
  volume DECIMAL(5,2) NOT NULL DEFAULT 0.60,
  PRIMARY KEY (shot_id, sound_effect_id),
  CONSTRAINT fk_shot_sfx_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE CASCADE,
  CONSTRAINT fk_shot_sfx_asset FOREIGN KEY (sound_effect_id) REFERENCES sound_effects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS bgm_tracks (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  path VARCHAR(1024) NOT NULL,
  sha256 CHAR(64) NULL,
  duration_seconds DECIMAL(12,4) NULL,
  default_volume DECIMAL(5,2) NOT NULL DEFAULT 0.18,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_bgm_path (path(768))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS episode_bgm (
  episode_id BIGINT UNSIGNED NOT NULL,
  bgm_id BIGINT UNSIGNED NOT NULL,
  volume DECIMAL(5,2) NOT NULL DEFAULT 0.18,
  PRIMARY KEY (episode_id, bgm_id),
  CONSTRAINT fk_episode_bgm_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
  CONSTRAINT fk_episode_bgm_track FOREIGN KEY (bgm_id) REFERENCES bgm_tracks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS subtitles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  episode_id BIGINT UNSIGNED NOT NULL,
  shot_id BIGINT UNSIGNED NULL,
  sequence_no INT NOT NULL,
  start_seconds DECIMAL(12,3) NOT NULL,
  end_seconds DECIMAL(12,3) NOT NULL,
  speaker VARCHAR(160) NULL,
  content TEXT NOT NULL,
  path VARCHAR(1024) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_subtitles_episode_time (episode_id, start_seconds),
  CONSTRAINT fk_subtitles_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
  CONSTRAINT fk_subtitles_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS production_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  episode_id BIGINT UNSIGNED NOT NULL,
  mode VARCHAR(32) NOT NULL DEFAULT 'ManualReview',
  status VARCHAR(32) NOT NULL DEFAULT 'Queued',
  total_shots INT NOT NULL DEFAULT 0,
  completed_shots INT NOT NULL DEFAULT 0,
  failed_shots INT NOT NULL DEFAULT 0,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  last_error TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_production_runs_episode_created (episode_id, created_at),
  CONSTRAINT fk_production_runs_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  CONSTRAINT fk_production_runs_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS project_templates (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name VARCHAR(160) NOT NULL,
  template_type VARCHAR(64) NOT NULL,
  description TEXT NULL,
  config_json JSON NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_project_templates_name_type (name, template_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
