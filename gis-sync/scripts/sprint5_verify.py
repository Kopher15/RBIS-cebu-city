"""
Sprint 5 verification harness.

End-to-end test of the full orchestrator path via the PowerShell launcher.
Mutates prod (tags a known row), invokes run-sync.ps1, asserts the upsert
overwrote the tag with the stage value, then restores the tagged row.

Run from project root:
    cd C:\\gis-sync
    $env:PYTHONPATH = "C:\\gis-sync\\src"
    python scripts/sprint5_verify.py
"""

import sys
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lib.db import connect
from lib.logger import get_logger

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sync.config.json"
LAUNCHER = Path(__file__).resolve().parent / "run-sync.ps1"
TAG_VALUE = "__SPRINT5_VERIFY_TAG__"

logger = get_logger(
    json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["log_dir"],
    "sprint5_verify",
)


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def snapshot_prod_counts(cur) -> dict:
    cur.execute(
        "SELECT COUNT(*) FILTER (WHERE NOT is_deleted) AS active, "
        "COUNT(*) FILTER (WHERE is_deleted) AS deleted, "
        "COUNT(*) AS total FROM public.road_inventory"
    )
    active, deleted, total = cur.fetchone()
    return {"total": total, "active": active, "deleted": deleted}


def pick_test_rid(cur) -> int:
    """Pick an arbitrary active r_id from prod to use as the tag target."""
    cur.execute(
        "SELECT r_id FROM public.road_inventory "
        "WHERE NOT is_deleted AND r_id IS NOT NULL "
        "ORDER BY r_id LIMIT 1"
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("No active rows in prod to use as test target")
    return row[0]


def snapshot_row(cur, r_id: int) -> dict:
    cur.execute(
        "SELECT r_id, r_name, is_deleted, deleted_at "
        "FROM public.road_inventory WHERE r_id = %s",
        (r_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"r_id={r_id} not found in prod")
    return {
        "r_id": row[0],
        "r_name": row[1],
        "is_deleted": row[2],
        "deleted_at": row[3],
    }


def get_max_sync_log_id(cur) -> int:
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM public.sync_log")
    return cur.fetchone()[0]


def get_sync_log_row(cur, run_id: int) -> dict:
    cur.execute(
        "SELECT id, status, inserted_count, updated_count, soft_deleted_count, "
        "un_deleted_count, backup_table, elapsed_seconds, error_message "
        "FROM public.sync_log WHERE id = %s",
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "status": row[1],
        "inserted": row[2],
        "updated": row[3],
        "soft_deleted": row[4],
        "un_deleted": row[5],
        "backup_table": row[6],
        "elapsed_seconds": row[7],
        "error_message": row[8],
    }


def main() -> int:
    logger.info("=== Sprint 5 verify: starting ===")
    cfg = load_config()
    logger.info("Config loaded")

    if not LAUNCHER.is_file():
        logger.error("Launcher not found: %s", LAUNCHER)
        return 1

    # ----- 1. Capture before-state -----
    with connect(cfg) as conn:
        with conn.cursor() as cur:
            before_counts = snapshot_prod_counts(cur)
            rid_tag = pick_test_rid(cur)
            snap = snapshot_row(cur, rid_tag)
            max_id_before = get_max_sync_log_id(cur)
    logger.info("Pre-test prod counts: %s", before_counts)
    logger.info("Test r_id selected: %d (original r_name=%r)", rid_tag, snap["r_name"])
    logger.info("sync_log max id before: %d", max_id_before)

    # ----- 2. Mutate prod: tag the chosen row -----
    with connect(cfg) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.road_inventory SET r_name = %s WHERE r_id = %s",
                    (TAG_VALUE, rid_tag),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Failed to tag prod r_id=%d" % rid_tag)
            conn.commit()
            logger.info("Prod tagged: r_id=%d set to %r", rid_tag, TAG_VALUE)
        except Exception:
            conn.rollback()
            logger.exception("Prod mutation failed; aborting")
            return 1

    # ----- 3. Invoke launcher via subprocess -----
    logger.info("Invoking launcher: %s", LAUNCHER)
    proc = subprocess.run(
        [
            "powershell.exe",
            "-ExecutionPolicy", "Bypass",
            "-NoProfile",
            "-File", str(LAUNCHER),
        ],
        capture_output=True,
        text=True,
        cwd=str(LAUNCHER.parent.parent),
    )
    logger.info("Launcher exit code: %d", proc.returncode)
    logger.info("Launcher stdout (last 500 chars): %s", proc.stdout[-500:] if proc.stdout else "")
    if proc.stderr:
        logger.warning("Launcher stderr: %s", proc.stderr[s-500:])

    # ----- 4. Assertions -----
    failures = []

    if proc.returncode != 0:
        failures.append(f"Launcher exit code {proc.returncode} (expected 0)")

    # Console output should have appeared (verbose mode is default)
    if proc.stdout and "Sync run SUCCESS" not in proc.stdout:
        failures.append("Launcher stdout missing 'Sync run SUCCESS' marker")
    elif not proc.stdout:
        failures.append("Launcher produced no stdout (verbose mode should output)")

    # Find the new sync_log row
    with connect(cfg) as conn:
        with conn.cursor() as cur:
            max_id_after = get_max_sync_log_id(cur)
            if max_id_after <= max_id_before:
                failures.append(
                    f"No new sync_log row created (before={max_id_before}, after={max_id_after})"
                )
                run_id = None
                sync_row = None
            else:
                run_id = max_id_after
                sync_row = get_sync_log_row(cur, run_id)
                logger.info("New sync_log row: %s", sync_row)

    if sync_row is not None:
        if sync_row["status"] != "success":
            failures.append(f"sync_log.status={sync_row['status']!r} (expected 'success')")
        if sync_row["updated"] < 7000:
            failures.append(f"sync_log.updated_count={sync_row['updated']} suspiciously low")
        if sync_row["error_message"] is not None:
            failures.append(f"sync_log.error_message is not null: {sync_row['error_message']!r}")
        if not sync_row["backup_table"]:
            failures.append("sync_log.backup_table is empty")

    # Verify the tag was overwritten by stage value
    with connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r_name FROM public.road_inventory WHERE r_id = %s",
                (rid_tag,),
            )
            current_name = cur.fetchone()[0]
    if current_name == TAG_VALUE:
        failures.append(
            f"Tag NOT overwritten: r_id={rid_tag} still has r_name={TAG_VALUE!r}"
        )
    elif current_name == snap["r_name"]:
        logger.info(
            "PASS: tag overwritten by stage value (r_name now %r)", current_name
        )
    else:
        # Tag was overwritten, but to something other than the original.
        # That's fine - it means stage had a different value than prod did,
        # which can happen if Mergin updated this row. Still proves upsert ran.
        logger.info(
            "PASS: tag overwritten by stage value (was %r, now %r)",
            TAG_VALUE, current_name,
        )

    # Verify the backup table exists and has rows
    if sync_row and sync_row["backup_table"]:
        bk = sync_row["backup_table"]
        with connect(cfg) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    (bk,),
                )
                exists = cur.fetchone()[0] == 1
                if not exists:
                    failures.append(f"Backup table {bk} not found")
                else:
                    cur.execute(f'SELECT COUNT(*) FROM public."{bk}"')
                    bk_count = cur.fetchone()[0]
                    if bk_count < 7000:
                        failures.append(
                            f"Backup table {bk} has only {bk_count} rows"
                        )
                    else:
                        logger.info(
                            "PASS: backup table %s exists with %d rows", bk, bk_count
                        )

    # ----- 5. Verify post-run prod counts unchanged from before -----
    with connect(cfg) as conn:
        with conn.cursor() as cur:
            after_counts = snapshot_prod_counts(cur)
    logger.info("Post-run prod counts: %s", after_counts)
    if before_counts != after_counts:
        failures.append(
            f"Prod counts changed: before={before_counts}, after={after_counts}"
        )
    else:
        logger.info("PASS: prod row counts unchanged")

    # ----- 6. Restore tagged row to original value -----
    # (The current value came from stage, which matches the .gpkg. Original
    # snap["r_name"] is what was in prod before our test mutation. If they
    # differ, the .gpkg has newer data than prod did - but for verify
    # purposes we just want to leave prod in the state we found it.)
    with connect(cfg) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.road_inventory SET r_name = %s WHERE r_id = %s",
                    (snap["r_name"], rid_tag),
                )
            conn.commit()
            logger.info(
                "Restored r_id=%d r_name to original value %r",
                rid_tag, snap["r_name"],
            )
        except Exception:
            conn.rollback()
            logger.exception("Restore failed")
            failures.append("Restore of tagged row failed")

    # ----- 7. Final report -----
    print("")
    print("=" * 60)
    if failures:
        print("SPRINT 5 VERIFICATION: FAILED")
        print("=" * 60)
        for f in failures:
            print("  FAIL: %s" % f)
        return 1
    else:
        print("SPRINT 5 VERIFICATION: ALL CHECKS PASSED")
        print("=" * 60)
        if sync_row:
            print(f"  run_id:        {sync_row['id']}")
            print(f"  inserted:      {sync_row['inserted']}")
            print(f"  updated:       {sync_row['updated']}")
            print(f"  soft_deleted:  {sync_row['soft_deleted']}")
            print(f"  un_deleted:    {sync_row['un_deleted']}")
            print(f"  backup_table:  {sync_row['backup_table']}")
            print(f"  elapsed:       {sync_row['elapsed_seconds']}s")
            print(f"  exit_code:     {proc.returncode}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
