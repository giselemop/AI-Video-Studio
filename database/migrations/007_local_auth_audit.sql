-- Local-only administrator session and security audit trail. This migration is additive.
CREATE TABLE IF NOT EXISTS admin_sessions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  token_hash CHAR(64) NOT NULL,
  csrf_hash CHAR(64) NOT NULL,
  username VARCHAR(128) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'Administrator',
  client_ip VARCHAR(64) NULL,
  user_agent VARCHAR(512) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  expires_at DATETIME(3) NOT NULL,
  last_seen_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  revoked_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admin_sessions_token_hash (token_hash),
  KEY ix_admin_sessions_active (expires_at, revoked_at),
  KEY ix_admin_sessions_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS security_audit_events (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id BIGINT UNSIGNED NULL,
  actor VARCHAR(128) NULL,
  role VARCHAR(32) NULL,
  action VARCHAR(96) NOT NULL,
  method VARCHAR(12) NOT NULL,
  path VARCHAR(512) NOT NULL,
  request_id VARCHAR(128) NULL,
  client_ip VARCHAR(64) NULL,
  outcome VARCHAR(32) NOT NULL,
  details_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY ix_security_audit_events_created (created_at),
  KEY ix_security_audit_events_actor (actor, created_at),
  KEY ix_security_audit_events_action (action, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
