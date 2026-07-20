"""
Sprint 3 verification harness.

Runs end-to-end against the live DB:
  1. Snapshot column count of prod.
  2. Add a synthetic test column to the stage table.
  3. Run the reconciler -- confirm prod gains the column.
  4. Run the backup service -- confirm a new bak_ table appears with same row count.
  5. Confirm column map covers every non-excluded stage column.
  6. Clean up: drop the synthetic test column from both stage and prod.

This is an integration test, not a unit test. It MUTATES prod (adds and then
drops one column) so do NOT run during a real sync window. Safe outside.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lib.db import connect, load_config
from lib.logger import get_logger
from services.schema_reconciler import reconcile, EXCLUDED_STAGE_COLUMNS
from services.backup_service import create_backup, list_backups


TEST_COL = "sprint3_test_col"


def main() -> int:
    cfg = load_config(os.path.join("config", "sync.config.json"))
    log = get_logger(cfg["log_dir"])
    log.info("=== Sprint 3 verification ===")
    prod = cfg["target_table"]
    stage = cfg["stage_table"]

    with connect(cfg) as conn:
        with conn.cursor() as cur:
            # 1. Initial state
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s", (prod,))
            prod_cols_before = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM public.{prod}")
            prod_rows = cur.fetchone()[0]

            # 2. Inject a synthetic stage column
            cur.execute(
                f'ALTER TABLE public.{stage} '
                f'ADD COLUMN IF NOT EXISTS "{TEST_COL}" text'
            )
        conn.commit()

    print(f"  prod columns before: {prod_cols_before}")
    print(f"  prod rows: {prod_rows}")
    print(f"  injected stage column: {TEST_COL}")

    # 3. Run reconciler
    result = reconcile(cfg)
    added_names = [c for c, _ in result["added"]]
    print(f"  reconciler added: {added_names}")
    if TEST_COL not in added_names:
        print(f"FAIL: reconciler did not add {TEST_COL} to prod", file=sys.stderr)
        return 1

    # 5. Verify mapping coverage
    with connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s", (stage,))
            all_stage = {r[0] for r in cur.fetchall()}
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s", (prod,))
            prod_cols_after = {r[0] for r in cur.fetchall()}

    expected_mapped = {c for c in all_stage if c.lower() not in EXCLUDED_STAGE_COLUMNS}
    missing = expected_mapped - set(result["mapped"].keys())
    if missing:
        print(f"FAIL: stage columns not mapped: {missing}", file=sys.stderr)
        return 1
    if TEST_COL not in prod_cols_after:
        print(f"FAIL: {TEST_COL} did not appear in prod after reconcile", file=sys.stderr)
        return 1
    print(f"  prod columns after reconcile: {len(prod_cols_after)} (was {prod_cols_before})")
    print(f"  mapping covers all {len(expected_mapped)} relevant stage columns")

    # 4. Run backup service
    backups_before = set(list_backups(cfg))
    bak = create_backup(cfg)
    backups_after = set(list_backups(cfg))
    new_backups = backups_after - backups_before
    if bak not in new_backups:
        print(f"FAIL: backup table {bak} not found after create_backup", file=sys.stderr)
        return 1

    with connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM public.{bak}")
            bak_rows = cur.fetchone()[0]
    if bak_rows != prod_rows:
        print(f"FAIL: backup row count {bak_rows} != prod row count {prod_rows}", file=sys.stderr)
        return 1
    print(f"  backup created: {bak} ({bak_rows} rows)")

    # 6. Cleanup
    with connect(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute(f'ALTER TABLE public.{prod} DROP COLUMN IF EXISTS "{TEST_COL}"')
            cur.execute(f'ALTER TABLE public.{stage} DROP COLUMN IF EXISTS "{TEST_COL}"')
        conn.commit()
    print(f"  cleanup: dropped {TEST_COL} from prod and stage")
    print(f"  NOTE: backup table {bak} retained (will be cleaned up after retain_backups_days)")

    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
