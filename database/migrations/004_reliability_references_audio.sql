-- AI Video Studio 可靠任务、参考资产和音频预检迁移
-- 只新增字段、索引和事件表，不删除或覆盖已有任务、素材或成片。

CREATE TABLE IF NOT EXISTS task_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id BIGINT UNSIGNED NOT NULL,
  from_status VARCHAR(32) NULL,
  to_status VARCHAR(32) NOT NULL,
  actor VARCHAR(64) NOT NULL DEFAULT 'system',
  worker VARCHAR(128) NULL,
  reason TEXT NULL,
  state_version INT NOT NULL,
  comfy_prompt_id VARCHAR(128) NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_task_events_task_created (task_id, created_at),
  CONSTRAINT fk_task_events_task FOREIGN KEY (task_id) REFERENCES generation_tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
