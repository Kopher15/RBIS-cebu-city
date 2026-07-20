"""
upsert_engine.py — GeoPackage → PostGIS upsert with full attribute sync.

CRITICAL HISTORY: The previous version of this file only upserted (r_id, geom, is_deleted),
which silently dropped every other column on every sync. Field crew edits to r_con,
r_name, s_type, etc. never reached PostGIS, even though the script reported success.
This version writes ALL shared columns and reports accurate counts.

CONTRACT (locked decisions, do not change without architecture review):

  CONFLICT KEY:
    r_id — guaranteed unique by sql/003_unique_rid.sql.

  COLUMNS WRITTEN ON UPSERT (27 total):
    All columns shared between road_inventory_stage and road_inventory.
    See SHARED_COLUMNS list below.

  COLUMNS DELIBERATELY NOT WRITTEN (they live only in target):
    - id              -- target PK, auto-generated, never touched
    - "length (m)"    -- legacy duplicate of r_length, dashboard ignores
    - "est. cost"     -- legacy precomputed, dashboard recomputes from JSON rates
    - asphalt_cost    -- same
    - concreting_cost -- same
    - earthworks_cost -- same

  COLUMNS RECOMPUTED FROM GEOMETRY:
    - r_length := ST_Length(EXCLUDED.geom::geography)
      Recomputed on every upsert from the new geometry. SRID 4326 → geography
      cast for accurate meters.

  SOFT-DELETE / UN-DELETE BEHAVIOR:
    - is_deleted=false and deleted_at=NULL on every upsert (un-deletes resurrected rows)
    - Rows present in target but absent from stage → soft-deleted
    - Counters distinguish inserts, updates, soft-deletes, un-deletes accurately

QUOTED IDENTIFIERS:
  Two columns have spaces: "date updated" and "photo 1".
  All identifiers are double-quoted via the q() helper.
"""

from lib.db import get_db_connection
from lib.logger import get_logger


# ── Schema contract ──────────────────────────────────────────────────────────
# Columns shared between road_inventory_stage (from ogr2ogr) and road_inventory
# (production target). r_id is excluded — it's the conflict key, not updateable.
# r_length is excluded — recomputed from geometry separately.
SHARED_COLUMNS = [
    "fid",
    "geom",
    "r_name",
    "s_type",
    "district",
    "r_width",
    "remarks",
    "date updated",   # quoted in SQL — has space
    "inspector",
    "photo 1",        # quoted in SQL — has space
    "r_con",
    "r_class",
    "r_importan",
    "brgy_name",
    "l_asphalt",
    "l_concrete",
    "l_earth",
    "l_gravel",
    "l_good",
    "l_fair",
    "l_poor",
    "l_bad",
    "l_mixed",
    "l_new",
    "d_flow",
    "terrain",
    "n_lanes",
]


def q(ident: str) -> str:
    """Double-quote an identifier safely (escape any embedded quotes)."""
    return '"' + ident.replace('"', '""') + '"'


def run_upsert(cfg, conn_string, column_map):
    """Run the upsert from stage → target. Returns accurate counts.

    Returns:
        dict with keys: inserted, updated, soft_deleted, un_deleted
    """
    logger = get_logger(cfg["log_dir"], "upsert_engine")
    target = cfg["target_table"]
    stage = cfg["stage_table"]

    # Pre-build the SQL fragments once
    quoted_cols = [q(c) for c in SHARED_COLUMNS]
    insert_col_list = ", ".join(["r_id"] + quoted_cols + ["is_deleted", "deleted_at"])
    select_col_list = ", ".join(["r_id"] + quoted_cols + ["false", "NULL"])

    update_setters = [f"{q(c)} = EXCLUDED.{q(c)}" for c in SHARED_COLUMNS]
    update_setters.append("r_length = ST_Length(EXCLUDED.geom::geography)")
    update_setters.append("is_deleted = false")
    update_setters.append("deleted_at = NULL")
    update_clause = ",\n                    ".join(update_setters)

    with get_db_connection(conn_string) as conn:
        with conn.cursor() as cur:

            # ── Step 1: Snapshot pre-upsert is_deleted state ─────────────────
            # Needed for accurate un-delete counter. Temp table dies on COMMIT.
            cur.execute(f"""
                CREATE TEMP TABLE _pre_state ON COMMIT DROP AS
                SELECT r_id, is_deleted FROM {target};
            """)

            # ── Step 2: Upsert with xmax-trick to count inserts vs updates ───
            # On a fresh INSERT, xmax = 0. On an UPDATE (conflict path),
            # xmax is the old transaction ID (non-zero). The CTE captures
            # the per-row outcome; the outer SELECT aggregates counts and
            # cross-references _pre_state to detect un-deletes.
            upsert_sql = f"""
                WITH upsert_result AS (
                    INSERT INTO {target} ({insert_col_list})
                    SELECT {select_col_list}
                    FROM {stage}
                    ON CONFLICT (r_id) DO UPDATE SET
                        {update_clause}
                    RETURNING r_id, (xmax = 0) AS was_insert
                )
                SELECT
                    COUNT(*) FILTER (WHERE was_insert) AS inserted,
                    COUNT(*) FILTER (WHERE NOT was_insert) AS updated,
                    COUNT(*) FILTER (
                        WHERE NOT was_insert
                          AND r_id IN (SELECT r_id FROM _pre_state WHERE is_deleted = true)
                    ) AS un_deleted
                FROM upsert_result;
            """
            cur.execute(upsert_sql)
            row = cur.fetchone()
            inserted, updated, un_deleted = int(row[0]), int(row[1]), int(row[2])

            # ── Step 3: Soft-delete rows present in target but absent from stage
            del_sql = f"""
                UPDATE {target} t
                SET is_deleted = true,
                    deleted_at = now()
                WHERE t.is_deleted = false
                  AND NOT EXISTS (
                      SELECT 1 FROM {stage} s WHERE s.r_id = t.r_id
                  );
            """
            cur.execute(del_sql)
            soft_del = cur.rowcount

            logger.info(
                f"Upsert complete: inserted={inserted}, updated={updated}, "
                f"soft_deleted={soft_del}, un_deleted={un_deleted}"
            )

            return {
                "inserted": inserted,
                "updated": updated,
                "soft_deleted": soft_del,
                "un_deleted": un_deleted,
            }
