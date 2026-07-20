-- Sprint 4 prerequisite: unique index on r_id for ON CONFLICT target.
-- Pre-check guards against bad data blocking the index creation.

DO $$
DECLARE
    null_count INTEGER;
    dup_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count
    FROM public.road_inventory
    WHERE r_id IS NULL;

    IF null_count > 0 THEN
        RAISE EXCEPTION 'Cannot create unique index: % rows have NULL r_id', null_count;
    END IF;

    SELECT COUNT(*) INTO dup_count
    FROM (
        SELECT r_id
        FROM public.road_inventory
        GROUP BY r_id
        HAVING COUNT(*) > 1
    ) dups;

    IF dup_count > 0 THEN
        RAISE EXCEPTION 'Cannot create unique index: % duplicate r_id values found', dup_count;
    END IF;

    RAISE NOTICE 'Pre-check passed: r_id is unique and non-null';
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_road_inventory_r_id
    ON public.road_inventory (r_id);

COMMENT ON INDEX public.idx_road_inventory_r_id IS
    'Unique index on r_id (Mergin-stable join key). Required for upsert ON CONFLICT target.';