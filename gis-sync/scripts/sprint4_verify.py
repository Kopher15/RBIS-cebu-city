"""
Sprint 4 verification harness.

End-to-end test of the upsert engine. Idempotent: snapshots prod state,
runs three mutation scenarios, asserts correct merge behavior, then restores
prod to its pre-test state.

Run from project root:
    cd C:\\gis-sync
    $env:PYTHONPATH = "C:\\gis-sync\\src"
    python scripts/sprint4_verify.py
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import json
from lib.db import connect
from lib.logger import get_logger
from services.gpkg_loader import load_gpkg_to_stage
from services.schema_reconciler import reconcile
from services.upsert_engine import run_upsert

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.DEBUG)
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_root = logging.getLogger()
_root.addHandler(_console)
if _root.level > logging.INFO or _root.level == logging.NOTSET:
    _root.setLevel(logging.INFO)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sync.config.json"
logger = get_logger(json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["log_dir"], "sprint4_verify")
SYNTHETIC_RID = -999999
TAG_VALUE = "__SPRINT4_VERIFY_TAG__"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def snapshot_prod_counts(cur) -> dict:
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE is_deleted = FALSE) AS active,
            COUNT(*) FILTER (WHERE is_deleted = TRUE) AS deleted
        FROM public.road_inventory
    """)
    total, active, deleted = cur.fetchone()
    return {"total": total, "active": active, "deleted": deleted}


def pick_test_rids(cur) -> tuple:
    cur.execute("""
        SELECT p.r_id FROM public.road_inventory p
        WHERE p.is_deleted = FALSE
          AND p.r_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM public.road_inventory_stage s WHERE s.r_id = p.r_id)
        ORDER BY random() LIMIT 2
    """)
    rows = cur.fetchall()
    if len(rows) < 2:
        raise RuntimeError("Need at least 2 active rows present in both prod and stage")
    return rows[0][0], rows[1][0]


def snapshot_row(cur, r_id):
    cur.execute("""
        SELECT r_name, is_deleted, deleted_at
        FROM public.road_inventory WHERE r_id = %s
    """, (r_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return {"r_name": row[0], "is_deleted": row[1], "deleted_at": row[2]}


def get_synthetic_geom_bytes(cur) -> bytes:
    cur.execute("SELECT ST_AsEWKB(geom) FROM public.road_inventory_stage LIMIT 1")
    return bytes(cur.fetchone()[0])


def main() -> int:
    logger.info("=== Sprint 4 verify: starting ===")
    cfg = load_config()
    logger.info("Config loaded")

    with connect(cfg) as conn:
        try:
            with conn.cursor() as cur:
                # Pre-cleanup: remove any synthetic rows left over from prior
                # failed runs. Idempotent.
                cur.execute(
                    "DELETE FROM public.road_inventory_stage WHERE r_id = %s",
                    (SYNTHETIC_RID,),
                )
                if cur.rowcount > 0:
                    logger.info("Pre-cleanup: removed %d stale synthetic rows", cur.rowcount)
                cur.execute(
                    "DELETE FROM public.road_inventory WHERE r_id = %s",
                    (SYNTHETIC_RID,),
                )
                if cur.rowcount > 0:
                    logger.info("Pre-cleanup: removed %d stale synthetic prod rows", cur.rowcount)

                before = snapshot_prod_counts(cur)
                logger.info("Pre-test prod counts: %s", before)

                rid_tag, rid_delete = pick_test_rids(cur)
                logger.info("Test r_ids selected: tag=%d, delete=%d", rid_tag, rid_delete)

                snap_tag = snapshot_row(cur, rid_tag)
                snap_delete = snapshot_row(cur, rid_delete)
                logger.info("Snapshots captured")

                cur.execute(
                    "UPDATE public.road_inventory_stage SET r_name = %s WHERE r_id = %s",
                    (TAG_VALUE, rid_tag),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Failed to tag r_id=%d in stage" % rid_tag)
                logger.info("Mutation A: tagged r_id=%d", rid_tag)

                cur.execute(
                    "DELETE FROM public.road_inventory_stage WHERE r_id = %s",
                    (rid_delete,),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Failed to delete r_id=%d from stage" % rid_delete)
                logger.info("Mutation B: deleted r_id=%d", rid_delete)

                synthetic_geom = get_synthetic_geom_bytes(cur)
                cur.execute(
                    "INSERT INTO public.road_inventory_stage (r_id, r_name, geom) VALUES (%s, %s, ST_GeomFromEWKB(%s))",
                    (SYNTHETIC_RID, "SYNTHETIC_VERIFY_ROW", synthetic_geom),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Failed to insert synthetic row in stage")
                logger.info("Mutation C: inserted synthetic r_id=%d", SYNTHETIC_RID)

            conn.commit()
            logger.info("Stage mutations committed")
        except Exception:
            conn.rollback()
            logger.exception("Stage mutation phase failed; aborting")
            return 1

    recon_result = reconcile(cfg)
    column_map = recon_result["mapped"]
    logger.info("Reconciler returned %d column mappings", len(column_map))

    try:
        result = run_upsert(cfg, column_map)
        logger.info("Upsert result: %s", result)
    except Exception:
        logger.exception("Upsert failed")
        return 1

    restore_failed = False
    try:
        with connect(cfg) as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT r_name FROM public.road_inventory WHERE r_id = %s", (rid_tag,))
                    actual_name = cur.fetchone()[0]
                    if actual_name != TAG_VALUE:
                        raise AssertionError("Tag did not propagate: got %r" % actual_name)
                    logger.info("PASS: tagged r_name propagated")

                    cur.execute("SELECT is_deleted, deleted_at FROM public.road_inventory WHERE r_id = %s", (rid_delete,))
                    is_del, del_at = cur.fetchone()
                    if not is_del:
                        raise AssertionError("r_id=%d should be soft-deleted" % rid_delete)
                    if del_at is None:
                        raise AssertionError("r_id=%d deleted_at should be set" % rid_delete)
                    logger.info("PASS: missing r_id soft-deleted")

                    cur.execute("SELECT id, r_id, is_deleted FROM public.road_inventory WHERE r_id = %s", (SYNTHETIC_RID,))
                    row = cur.fetchone()
                    if row is None:
                        raise AssertionError("Synthetic r_id was not inserted into prod")
                    new_id, _, syn_deleted = row
                    if new_id is None or new_id <= 0:
                        raise AssertionError("Synthetic row id not sequence-assigned")
                    if syn_deleted:
                        raise AssertionError("Synthetic row should be active")
                    logger.info("PASS: synthetic r_id inserted (id=%d)", new_id)

                    if result["inserted"] < 1:
                        raise AssertionError("Expected at least 1 insert")
                    if result["soft_deleted"] < 1:
                        raise AssertionError("Expected at least 1 soft-delete")
                    logger.info("PASS: result counts consistent")

                    logger.info("Restoring prod to pre-test state")
                    cur.execute("UPDATE public.road_inventory SET r_name = %s WHERE r_id = %s", (snap_tag["r_name"], rid_tag))
                    cur.execute(
                        "UPDATE public.road_inventory SET is_deleted = %s, deleted_at = %s WHERE r_id = %s",
                        (snap_delete["is_deleted"], snap_delete["deleted_at"], rid_delete),
                    )
                    cur.execute("DELETE FROM public.road_inventory WHERE r_id = %s", (SYNTHETIC_RID,))
                conn.commit()
                logger.info("Prod restored")
            except Exception:
                conn.rollback()
                logger.exception("Assertion or restore failed")
                restore_failed = True
    except Exception:
        logger.exception("Connection failure during assert/restore phase")
        restore_failed = True

    if restore_failed:
        return 1

    logger.info("Restoring stage via loader")
    try:
        load_gpkg_to_stage(cfg)
        logger.info("Stage restored")
    except Exception:
        logger.exception("Stage restore via loader failed")
        return 1

    with connect(cfg) as conn:
        with conn.cursor() as cur:
            after = snapshot_prod_counts(cur)
    logger.info("Post-test prod counts: %s", after)
    if before != after:
        logger.error("Prod state not fully restored: before=%s, after=%s", before, after)
        return 1
    logger.info("PASS: prod state fully restored")

    print("")
    print("=" * 60)
    print("SPRINT 4 VERIFICATION: ALL CHECKS PASSED")
    print("=" * 60)
    print("  inserted:     %d" % result["inserted"])
    print("  updated:      %d" % result["updated"])
    print("  soft_deleted: %d" % result["soft_deleted"])
    print("  un_deleted:   %d" % result["un_deleted"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
