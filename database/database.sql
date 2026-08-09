-- AI Video Studio schema for MySQL 8.0+
-- Media, model weights and large binaries stay on disk. The database stores metadata and paths only.
CREATE DATABASE IF NOT EXISTS `ai_video_studio`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE `ai_video_studio`;

CREATE TABLE IF NOT EXISTS `projects` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(160) NOT NULL,
  `slug` VARCHAR(160) NOT NULL,
  `description` TEXT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'Active',
  `root_path` VARCHAR(512) NULL,
  `cover_path` VARCHAR(1024) NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_projects_slug` (`slug`),
  KEY `ix_projects_status_updated` (`status`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `episodes` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `project_id` BIGINT UNSIGNED NOT NULL,
  `episode_number` INT NOT NULL DEFAULT 1,
  `name` VARCHAR(160) NOT NULL,
  `description` TEXT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'Draft',
  `target_seconds` DECIMAL(10,3) NOT NULL DEFAULT 60,
  `output_fps` INT NOT NULL DEFAULT 30,
  `output_width` INT NOT NULL DEFAULT 1920,
  `output_height` INT NOT NULL DEFAULT 1080,
  `output_path` VARCHAR(1024) NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_episodes_project_number` (`project_id`, `episode_number`),
  KEY `ix_episodes_project_updated` (`project_id`, `updated_at`),
  CONSTRAINT `fk_episodes_project` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `characters` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `project_id` BIGINT UNSIGNED NULL,
  `name` VARCHAR(160) NOT NULL,
  `age_setting` VARCHAR(80) NULL,
  `face_features` TEXT NULL,
  `hair` TEXT NULL,
  `clothes` TEXT NULL,
  `body_ratio` VARCHAR(160) NULL,
  `fixed_prompt` TEXT NULL,
  `negative_prompt` TEXT NULL,
  `embedding_path` VARCHAR(1024) NULL,
  `lora_path` VARCHAR(1024) NULL,
  `anchor_path` VARCHAR(1024) NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_characters_project_name` (`project_id`, `name`),
  CONSTRAINT `fk_characters_project` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `character_references` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `character_id` BIGINT UNSIGNED NOT NULL,
  `path` VARCHAR(1024) NOT NULL,
  `kind` VARCHAR(32) NOT NULL DEFAULT 'identity',
  `is_anchor` TINYINT(1) NOT NULL DEFAULT 0,
  `width` INT NULL,
  `height` INT NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_character_references_character_anchor` (`character_id`, `is_anchor`),
  CONSTRAINT `fk_character_references_character` FOREIGN KEY (`character_id`) REFERENCES `characters` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `scenes` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `project_id` BIGINT UNSIGNED NULL,
  `name` VARCHAR(160) NOT NULL,
  `description` TEXT NULL,
  `fixed_prompt` TEXT NULL,
  `negative_prompt` TEXT NULL,
  `style` VARCHAR(160) NULL,
  `anchor_path` VARCHAR(1024) NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_scenes_project_name` (`project_id`, `name`),
  CONSTRAINT `fk_scenes_project` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `scene_references` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `scene_id` BIGINT UNSIGNED NOT NULL,
  `path` VARCHAR(1024) NOT NULL,
  `kind` VARCHAR(32) NOT NULL DEFAULT 'master',
  `is_anchor` TINYINT(1) NOT NULL DEFAULT 0,
  `width` INT NULL,
  `height` INT NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_scene_references_scene_anchor` (`scene_id`, `is_anchor`),
  CONSTRAINT `fk_scene_references_scene` FOREIGN KEY (`scene_id`) REFERENCES `scenes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `assets` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `project_id` BIGINT UNSIGNED NULL,
  `episode_id` BIGINT UNSIGNED NULL,
  `shot_id` BIGINT UNSIGNED NULL,
  `asset_type` VARCHAR(32) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `path` VARCHAR(1024) NOT NULL,
  `relative_path` VARCHAR(1024) NULL,
  `mime_type` VARCHAR(128) NULL,
  `size_bytes` BIGINT UNSIGNED NULL,
  `width` INT NULL,
  `height` INT NULL,
  `duration_seconds` DECIMAL(12,4) NULL,
  `fps` DECIMAL(10,4) NULL,
  `sha256` CHAR(64) NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_assets_project_type_created` (`project_id`, `asset_type`, `created_at`),
  KEY `ix_assets_episode_shot` (`episode_id`, `shot_id`),
  KEY `ix_assets_sha256` (`sha256`),
  CONSTRAINT `fk_assets_project` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_assets_episode` FOREIGN KEY (`episode_id`) REFERENCES `episodes` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `models` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  `model_type` VARCHAR(64) NOT NULL,
  `path` VARCHAR(1024) NOT NULL,
  `file_size_bytes` BIGINT UNSIGNED NULL,
  `sha256` CHAR(64) NULL,
  `vram_hint_mib` INT NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_models_path` (`path`(768)),
  KEY `ix_models_type` (`model_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `loras` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  `path` VARCHAR(1024) NOT NULL,
  `strength_model` DECIMAL(8,4) NOT NULL DEFAULT 1,
  `strength_clip` DECIMAL(8,4) NOT NULL DEFAULT 1,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_loras_path` (`path`(768))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `workflows` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(255) NOT NULL,
  `workflow_type` VARCHAR(64) NOT NULL,
  `path` VARCHAR(1024) NOT NULL,
  `model_name` VARCHAR(255) NULL,
  `parameter_mapping_json` JSON NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_workflows_path` (`path`(768)),
  KEY `ix_workflows_type_enabled` (`workflow_type`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `shots` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `project_id` BIGINT UNSIGNED NOT NULL,
  `episode_id` BIGINT UNSIGNED NOT NULL,
  `shot_number` INT NOT NULL,
  `title` VARCHAR(255) NOT NULL,
  `description` TEXT NULL,
  `scene_id` BIGINT UNSIGNED NULL,
  `character_ids_json` JSON NULL,
  `prompt` TEXT NULL,
  `negative_prompt` TEXT NULL,
  `workflow_id` BIGINT UNSIGNED NULL,
  `model_id` BIGINT UNSIGNED NULL,
  `lora_ids_json` JSON NULL,
  `seed` BIGINT NULL,
  `cfg_scale` DECIMAL(8,4) NULL,
  `steps` INT NULL,
  `width` INT NULL,
  `height` INT NULL,
  `frames` INT NULL,
  `fps` DECIMAL(10,4) NULL,
  `input_image_path` VARCHAR(1024) NULL,
  `motion_preset` VARCHAR(120) NULL,
  `camera_preset` VARCHAR(120) NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'Draft',
  `sort_order` INT NOT NULL DEFAULT 0,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_shots_episode_number` (`episode_id`, `shot_number`),
  KEY `ix_shots_project_episode_order` (`project_id`, `episode_id`, `sort_order`),
  KEY `ix_shots_scene` (`scene_id`),
  CONSTRAINT `fk_shots_project` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_shots_episode` FOREIGN KEY (`episode_id`) REFERENCES `episodes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_shots_scene` FOREIGN KEY (`scene_id`) REFERENCES `scenes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_shots_workflow` FOREIGN KEY (`workflow_id`) REFERENCES `workflows` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_shots_model` FOREIGN KEY (`model_id`) REFERENCES `models` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `generation_tasks` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `project_id` BIGINT UNSIGNED NULL,
  `episode_id` BIGINT UNSIGNED NULL,
  `shot_id` BIGINT UNSIGNED NULL,
  `task_type` VARCHAR(64) NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'Pending',
  `priority` INT NOT NULL DEFAULT 0,
  `attempts` INT NOT NULL DEFAULT 0,
  `max_retries` INT NOT NULL DEFAULT 2,
  `workflow_id` BIGINT UNSIGNED NULL,
  `input_json` JSON NULL,
  `progress` DECIMAL(6,3) NOT NULL DEFAULT 0,
  `comfy_prompt_id` VARCHAR(128) NULL,
  `error_message` TEXT NULL,
  `gpu_name` VARCHAR(255) NULL,
  `vram_peak_mib` INT NULL,
  `vram_free_mib` INT NULL,
  `gpu_utilization` DECIMAL(6,3) NULL,
  `queued_at` DATETIME(3) NULL,
  `started_at` DATETIME(3) NULL,
  `finished_at` DATETIME(3) NULL,
  `duration_ms` BIGINT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_tasks_queue` (`status`, `priority`, `created_at`),
  KEY `ix_tasks_project_created` (`project_id`, `created_at`),
  KEY `ix_tasks_shot` (`shot_id`),
  CONSTRAINT `fk_tasks_project` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_tasks_episode` FOREIGN KEY (`episode_id`) REFERENCES `episodes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_tasks_shot` FOREIGN KEY (`shot_id`) REFERENCES `shots` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_tasks_workflow` FOREIGN KEY (`workflow_id`) REFERENCES `workflows` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `generation_results` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `task_id` BIGINT UNSIGNED NOT NULL,
  `asset_id` BIGINT UNSIGNED NULL,
  `result_type` VARCHAR(64) NOT NULL,
  `path` VARCHAR(1024) NOT NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_results_task_created` (`task_id`, `created_at`),
  CONSTRAINT `fk_results_task` FOREIGN KEY (`task_id`) REFERENCES `generation_tasks` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_results_asset` FOREIGN KEY (`asset_id`) REFERENCES `assets` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `prompt_templates` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(160) NOT NULL,
  `template_type` VARCHAR(64) NOT NULL,
  `content` TEXT NOT NULL,
  `negative_prompt` TEXT NULL,
  `variables_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_prompt_templates_name_type` (`name`, `template_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `generation_presets` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(160) NOT NULL,
  `preset_type` VARCHAR(64) NOT NULL,
  `parameters_json` JSON NOT NULL,
  `description` TEXT NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_generation_presets_name_type` (`name`, `preset_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `system_settings` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `setting_key` VARCHAR(160) NOT NULL,
  `setting_value` TEXT NULL,
  `category` VARCHAR(64) NOT NULL DEFAULT 'system',
  `is_secret` TINYINT(1) NOT NULL DEFAULT 0,
  `updated_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_system_settings_key` (`setting_key`),
  KEY `ix_system_settings_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `operation_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `level` VARCHAR(16) NOT NULL DEFAULT 'Info',
  `operation` VARCHAR(120) NOT NULL,
  `message` TEXT NOT NULL,
  `task_id` BIGINT UNSIGNED NULL,
  `metadata_json` JSON NULL,
  `created_at` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  KEY `ix_operation_logs_created` (`created_at`),
  KEY `ix_operation_logs_task` (`task_id`),
  CONSTRAINT `fk_operation_logs_task` FOREIGN KEY (`task_id`) REFERENCES `generation_tasks` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO `system_settings` (`setting_key`, `setting_value`, `category`) VALUES
  ('paths.models', 'C:\\install\\AI\\Models', 'paths'),
  ('paths.workflows', 'C:\\install\\AI\\Workflows', 'paths'),
  ('paths.data', 'C:\\install\\AI\\Data', 'paths'),
  ('queue.gpu_concurrency', '1', 'queue'),
  ('queue.min_free_vram_mib', '1024', 'queue')
ON DUPLICATE KEY UPDATE `setting_key` = VALUES(`setting_key`);

INSERT INTO `generation_presets` (`name`, `preset_type`, `parameters_json`, `description`) VALUES
  ('4070 人物图片稳定', 'Image', JSON_OBJECT('width', 768, 'height', 512, 'steps', 24, 'cfg', 6.5, 'sampler', 'dpmpp_2m', 'scheduler', 'karras'), 'SD1.5 半身人物，适合 RTX 4070 12GB'),
  ('4070 LTX 图生视频 5 秒', 'ImageToVideo', JSON_OBJECT('width', 512, 'height', 320, 'frames', 121, 'fps', 24, 'steps', 12, 'cfg', 3.0), 'LTX 2B FP8，单任务串行，约 5 秒'),
  ('短片输出 1080P 30fps', 'Enhancement', JSON_OBJECT('width', 1920, 'height', 1080, 'fps', 30, 'deflicker', TRUE, 'interpolate', TRUE), 'FFmpeg 去闪烁、插帧与 1080P 输出')
ON DUPLICATE KEY UPDATE `parameters_json` = VALUES(`parameters_json`), `description` = VALUES(`description`);
