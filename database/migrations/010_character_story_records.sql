-- Reuse the existing immutable ledger for references, casting and Shot context.
-- A single atomic ALTER preserves all rows and original entity types.
ALTER TABLE entity_versions
  DROP CHECK ck_entity_versions_type,
  ADD CONSTRAINT ck_entity_versions_type CHECK (entity_type IN
    ('Character','Scene','Prompt','Workflow','Voice','ProjectCast','EpisodeCast','ShotCast','KeyframeReview','LibraryReview','CharacterWorkflow'));
