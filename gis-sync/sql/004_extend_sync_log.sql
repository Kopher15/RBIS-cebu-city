-- sql/004_extend_sync_log.sql
-- Sprint 5.1: extend sync_log with un_deleted_count
--
-- Sprint 4's upsert_engine returns un_deleted (rows previously soft-deleted
-- that reappeared in the stage and were resurrected). sync_log was built in
-- Sprint 1 before this concept existed; this migration adds the column.
--
-- Idempotent: safe to re-run.

ALTER TABLE public.sync_log
    ADD COLUMN IF NOT EXISTS un_deleted_count integer NOT NULL DEFAULT 0;

-- Verify (no-op if column already existed before this run):
COMMENT ON COLUMN public.sync_log.un_deleted_count IS
    'Count of rows un-soft-deleted during upsert (resurrected from prior soft-delete).';
