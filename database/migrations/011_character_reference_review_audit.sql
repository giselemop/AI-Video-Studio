-- Repair the missing audit table already defined by migration009.
-- Idempotent, additive; does not approve/reject or rewrite any reference.
CREATE TABLE IF NOT EXISTS character_reference_reviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    character_id BIGINT UNSIGNED NOT NULL,
    reference_id BIGINT UNSIGNED NOT NULL,
    decision VARCHAR(24) NOT NULL,
    asset_version INT UNSIGNED NOT NULL,
    asset_sha256 CHAR(64) NOT NULL,
    reviewer VARCHAR(128) NOT NULL,
    note VARCHAR(1000) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY ix_character_reference_reviews_reference (reference_id, created_at),
    KEY ix_character_reference_reviews_character (character_id, created_at),
    CONSTRAINT fk_character_reference_reviews_character FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE,
    CONSTRAINT fk_character_reference_reviews_reference FOREIGN KEY (reference_id) REFERENCES character_references (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
