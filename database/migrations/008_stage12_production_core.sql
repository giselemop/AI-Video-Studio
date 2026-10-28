-- AI Video Studio stage 1 + stage 2 production core
-- Additive only: no existing row is updated or deleted by this file.
-- The application migrator guards column/index additions through information_schema.

CREATE TABLE IF NOT EXISTS production_profiles (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  profile_key VARCHAR(128) NOT NULL,
  version INT UNSIGNED NOT NULL,
  name VARCHAR(255) NOT NULL,
  content_json JSON NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  created_by VARCHAR(128) NOT NULL DEFAULT 'system',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_production_profiles_version (project_id, profile_key, version),
  UNIQUE KEY uq_production_profiles_content (project_id, profile_key, content_sha256),
  KEY ix_production_profiles_project_created (project_id, created_at),
  CONSTRAINT fk_production_profiles_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS project_production_profile_bindings (
  project_id BIGINT UNSIGNED NOT NULL,
  production_profile_id BIGINT UNSIGNED NOT NULL,
  bound_by VARCHAR(128) NOT NULL DEFAULT 'system',
  bound_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (project_id),
  KEY ix_profile_bindings_profile (production_profile_id),
  CONSTRAINT fk_profile_bindings_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  CONSTRAINT fk_profile_bindings_profile FOREIGN KEY (production_profile_id) REFERENCES production_profiles(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS entity_versions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  entity_type VARCHAR(32) NOT NULL,
  entity_id BIGINT UNSIGNED NOT NULL,
  version INT UNSIGNED NOT NULL,
  payload_json JSON NOT NULL,
  source_asset_ids_json JSON NULL,
  payload_sha256 CHAR(64) NOT NULL,
  note VARCHAR(500) NULL,
  created_by VARCHAR(128) NOT NULL DEFAULT 'system',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_entity_versions_version (entity_type, entity_id, version),
  UNIQUE KEY uq_entity_versions_content (entity_type, entity_id, payload_sha256),
  KEY ix_entity_versions_project_type_created (project_id, entity_type, created_at),
  CONSTRAINT fk_entity_versions_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
  CONSTRAINT ck_entity_versions_type CHECK (entity_type IN ('Character','Scene','Prompt','Workflow','Voice'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS shot_plans (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  episode_id BIGINT UNSIGNED NOT NULL,
  shot_id BIGINT UNSIGNED NOT NULL,
  version INT UNSIGNED NOT NULL,
  production_profile_id BIGINT UNSIGNED NOT NULL,
  character_version_ids_json JSON NOT NULL,
  scene_version_id BIGINT UNSIGNED NULL,
  prompt_version_id BIGINT UNSIGNED NOT NULL,
  workflow_version_id BIGINT UNSIGNED NOT NULL,
  voice_version_id BIGINT UNSIGNED NULL,
  input_asset_ids_json JSON NULL,
  parameters_json JSON NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  created_by VARCHAR(128) NOT NULL DEFAULT 'system',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_shot_plans_version (shot_id, version),
  UNIQUE KEY uq_shot_plans_content (shot_id, content_sha256),
  KEY ix_shot_plans_episode_created (episode_id, created_at),
  KEY ix_shot_plans_profile (production_profile_id),
  CONSTRAINT fk_shot_plans_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
  CONSTRAINT fk_shot_plans_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE RESTRICT,
  CONSTRAINT fk_shot_plans_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_shot_plans_profile FOREIGN KEY (production_profile_id) REFERENCES production_profiles(id) ON DELETE RESTRICT,
  CONSTRAINT fk_shot_plans_scene_version FOREIGN KEY (scene_version_id) REFERENCES entity_versions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_shot_plans_prompt_version FOREIGN KEY (prompt_version_id) REFERENCES entity_versions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_shot_plans_workflow_version FOREIGN KEY (workflow_version_id) REFERENCES entity_versions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_shot_plans_voice_version FOREIGN KEY (voice_version_id) REFERENCES entity_versions(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS task_attempts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id BIGINT UNSIGNED NOT NULL,
  attempt_no INT UNSIGNED NOT NULL,
  lease_token CHAR(36) NOT NULL,
  worker_id VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'Running',
  state_version INT NOT NULL,
  temp_relative_path VARCHAR(1024) NOT NULL,
  lease_expires_at DATETIME(3) NOT NULL,
  heartbeat_at DATETIME(3) NOT NULL,
  started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  finished_at DATETIME(3) NULL,
  failure_code VARCHAR(64) NULL,
  error_message TEXT NULL,
  output_manifest_id BIGINT UNSIGNED NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_attempts_task_no (task_id, attempt_no),
  UNIQUE KEY uq_task_attempts_lease_token (lease_token),
  KEY ix_task_attempts_worker_status (worker_id, status, heartbeat_at),
  CONSTRAINT fk_task_attempts_task FOREIGN KEY (task_id) REFERENCES generation_tasks(id) ON DELETE CASCADE,
  CONSTRAINT ck_task_attempts_status CHECK (status IN ('Running','Succeeded','Failed','Cancelled','Abandoned'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS asset_manifests (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id BIGINT UNSIGNED NOT NULL,
  episode_id BIGINT UNSIGNED NULL,
  shot_id BIGINT UNSIGNED NULL,
  task_id BIGINT UNSIGNED NULL,
  attempt_id BIGINT UNSIGNED NULL,
  source_kind VARCHAR(32) NOT NULL DEFAULT 'Task',
  production_profile_id BIGINT UNSIGNED NULL,
  shot_plan_id BIGINT UNSIGNED NULL,
  purpose VARCHAR(64) NOT NULL,
  version INT UNSIGNED NOT NULL,
  relative_path VARCHAR(1024) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  extension VARCHAR(16) NOT NULL,
  mime_type VARCHAR(128) NOT NULL,
  size_bytes BIGINT UNSIGNED NOT NULL,
  sha256 CHAR(64) NOT NULL,
  probe_json JSON NULL,
  input_manifest_json JSON NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'Ready',
  finalized_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uq_asset_manifests_path (relative_path(768)),
  UNIQUE KEY uq_asset_manifests_version (task_id, purpose, version),
  KEY ix_asset_manifests_project_purpose (project_id, purpose, created_at),
  KEY ix_asset_manifests_attempt (attempt_id),
  CONSTRAINT fk_asset_manifests_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
  CONSTRAINT fk_asset_manifests_episode FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE RESTRICT,
  CONSTRAINT fk_asset_manifests_shot FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_asset_manifests_task FOREIGN KEY (task_id) REFERENCES generation_tasks(id) ON DELETE RESTRICT,
  CONSTRAINT fk_asset_manifests_attempt FOREIGN KEY (attempt_id) REFERENCES task_attempts(id) ON DELETE RESTRICT,
  CONSTRAINT fk_asset_manifests_profile FOREIGN KEY (production_profile_id) REFERENCES production_profiles(id) ON DELETE RESTRICT,
  CONSTRAINT fk_asset_manifests_shot_plan FOREIGN KEY (shot_plan_id) REFERENCES shot_plans(id) ON DELETE RESTRICT,
  CONSTRAINT ck_asset_manifests_source CHECK (source_kind IN ('Task','Upload','Import')),
  CONSTRAINT ck_asset_manifests_status CHECK (status IN ('Staged','Ready','Quarantined','Superseded'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS artifact_publish_intents (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id BIGINT UNSIGNED NOT NULL,
  attempt_id BIGINT UNSIGNED NOT NULL,
  lease_token CHAR(36) NOT NULL,
  project_id BIGINT UNSIGNED NOT NULL,
  episode_id BIGINT UNSIGNED NULL,
  shot_id BIGINT UNSIGNED NULL,
  purpose VARCHAR(64) NOT NULL,
  temp_relative_path VARCHAR(1024) NOT NULL,
  final_relative_path VARCHAR(1024) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'Staging',
  sha256 CHAR(64) NULL,
  size_bytes BIGINT UNSIGNED NULL,
  error_message TEXT NULL,
  manifest_id BIGINT UNSIGNED NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  finalized_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_artifact_publish_intent (attempt_id, purpose, final_relative_path(640)),
  KEY ix_publish_intents_status_created (status, created_at),
  CONSTRAINT fk_publish_intents_task FOREIGN KEY (task_id) REFERENCES generation_tasks(id) ON DELETE CASCADE,
  CONSTRAINT fk_publish_intents_attempt FOREIGN KEY (attempt_id) REFERENCES task_attempts(id) ON DELETE CASCADE,
  CONSTRAINT fk_publish_intents_manifest FOREIGN KEY (manifest_id) REFERENCES asset_manifests(id) ON DELETE RESTRICT,
  CONSTRAINT ck_publish_intents_status CHECK (status IN ('Staging','Ready','NeedsReconcile','Rejected'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS llm_egress_audit (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  provider VARCHAR(64) NOT NULL,
  host VARCHAR(255) NOT NULL,
  model VARCHAR(255) NULL,
  prompt_chars INT UNSIGNED NOT NULL DEFAULT 0,
  max_tokens INT UNSIGNED NOT NULL DEFAULT 0,
  outcome VARCHAR(32) NOT NULL,
  duration_ms BIGINT UNSIGNED NULL,
  error_code VARCHAR(64) NULL,
  request_id VARCHAR(128) NULL,
  redacted_preview TEXT NULL,
  redirect_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
  timeout_ms INT UNSIGNED NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_llm_egress_audit_budget (created_at, outcome),
  KEY ix_llm_egress_audit_host (host, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Added by Stage12SchemaMigrator after information_schema guards:
-- generation_tasks: production_profile_id, shot_plan_id, input_asset_id,
-- active_attempt_id, lease_token, output_manifest_id
-- generation_results: attempt_id, manifest_id
-- task_events: attempt_id, lease_token, output_manifest_id
-- assets: manifest_id, purpose, version, status, source_attempt_id, immutable_path
