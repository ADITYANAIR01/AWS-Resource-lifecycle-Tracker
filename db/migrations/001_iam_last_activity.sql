-- =============================================================================
-- Migration 001 — IAM last-activity tracking
-- Adds resources.last_activity_at so the iam_user_inactive rule measures
-- real IAM activity (console login / access-key last used) instead of the
-- row's last_modified clock (which moves on tag/state upserts).
--
-- Idempotent — safe to run multiple times (IF NOT EXISTS throughout).
-- Run: psql -h <host> -U <user> -d <db> -f db/migrations/001_iam_last_activity.sql
-- =============================================================================

ALTER TABLE resources
    ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_resources_iam_last_activity
    ON resources(resource_type, last_activity_at)
    WHERE resource_type = 'iam_user';

-- One-shot backfill for pre-migration rows. New polls overwrite
-- last_activity_at on every upsert, so this is only a best-effort seed:
-- fall back to last_modified (row clock), never parse snapshot JSON.
UPDATE resources
SET last_activity_at = COALESCE(last_activity_at, last_modified)
WHERE resource_type = 'iam_user'
  AND last_activity_at IS NULL;
