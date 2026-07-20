-- 001_init_sync_log.sql
-- Idempotent: safe to run multiple times.

BEGIN;

-- 1. Soft-delete column on production table
ALTER TABLE public.road_inventory
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.road_inventory
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- 2. Operational log table
CREATE TABLE IF NOT EXISTS public.sync_log (
    id              BIGSERIAL PRIMARY KEY,
    run_started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_ended_at    TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('success', 'failed', 'running')),
    inserted_count  INTEGER NOT NULL DEFAULT 0,
    updated_count   INTEGER NOT NULL DEFAULT 0,
    soft_deleted_count INTEGER NOT NULL DEFAULT 0,
    schema_changes  JSONB,
    backup_table    TEXT,
    error_message   TEXT,
    elapsed_seconds NUMERIC(10, 3)
);

CREATE INDEX IF NOT EXISTS idx_sync_log_started
    ON public.sync_log (run_started_at DESC);

COMMIT;