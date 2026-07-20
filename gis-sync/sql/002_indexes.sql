-- 002_indexes.sql
-- Ensures upsert and API queries stay fast.

CREATE UNIQUE INDEX IF NOT EXISTS idx_road_inventory_id
    ON public.road_inventory (id);

CREATE INDEX IF NOT EXISTS idx_road_inventory_geom
    ON public.road_inventory USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_road_inventory_is_deleted
    ON public.road_inventory (is_deleted)
    WHERE is_deleted = FALSE;