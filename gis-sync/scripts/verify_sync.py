"""
verify_sync.py — Automated end-to-end test for the upsert engine.

Picks a known r_id, deliberately writes a sentinel value into the STAGE table,
runs the upsert, and asserts that the value landed in the TARGET table.

This bypasses ogr2ogr (no GeoPackage edit needed) so the test is fast and
deterministic. It tests the upsert engine itself, which is where the previous
bug lived.

EXIT CODES:
    0 = all assertions passed (sync engine works correctly)
    1 = at least one assertion failed (engine still broken — DO NOT use in prod)
    2 = harness error (DB connection, missing config, etc.)

USAGE:
    cd C:\\gis-sync
    python scripts\\verify_sync.py
"""
import sys
import os
import json
from datetime import datetime

# Add src to path so we can import the engine
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from lib.db import get_db_connection
from services.upsert_engine import run_upsert


SENTINEL_VALUE = f"VERIFY_TEST_{datetime.utcnow().strftime('%H%M%S')}"


def load_config():
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "sync.config.json"
    )
    with open(config_path) as f:
        return json.load(f)


def green(s):
    return f"\033[32m{s}\033[0m" if sys.stdout.isatty() else s


def red(s):
    return f"\033[31m{s}\033[0m" if sys.stdout.isatty() else s


def yellow(s):
    return f"\033[33m{s}\033[0m" if sys.stdout.isatty() else s


def main():
    print("=" * 70)
    print("  upsert_engine end-to-end verification")
    print("=" * 70)

    cfg = load_config()
    target = cfg["target_table"]
    stage = cfg["stage_table"]

    # Use the LOCAL destination only — never touch cloud during testing
    local_dest = next((d for d in cfg["destinations"] if d["name"] == "local"), None)
    if not local_dest:
        print(red("✗ No 'local' destination found in config. Aborting."))
        sys.exit(2)
    conn_string = local_dest["conn_string"]

    print(f"  Target: {target}")
    print(f"  Stage:  {stage}")
    print(f"  Sentinel: {SENTINEL_VALUE}")
    print()

    failures = []

    with get_db_connection(conn_string) as conn:
        with conn.cursor() as cur:

            # ── Pre-flight: pick a stable test row ───────────────────────────
            cur.execute(f"""
                SELECT r_id, r_con
                FROM {stage}
                WHERE r_id IS NOT NULL
                  AND r_id IN (SELECT r_id FROM {target})
                ORDER BY r_id
                LIMIT 1;
            """)
            test_row = cur.fetchone()
            if not test_row:
                print(red("✗ No test row found (stage and target have no overlapping r_id)."))
                print(red("  Run a normal sync first to populate both tables."))
                sys.exit(2)
            test_rid, original_rcon = test_row
            print(f"  Test r_id: {test_rid} (original r_con: {original_rcon!r})")
            print()

            # ── Capture target's current value before we touch anything ──────
            cur.execute(
                f'SELECT r_con FROM {target} WHERE r_id = %s;',
                (test_rid,),
            )
            target_before = cur.fetchone()[0]
            print(f"  Target r_con BEFORE: {target_before!r}")

            # ── Inject sentinel value into STAGE only ────────────────────────
            cur.execute(
                f'UPDATE {stage} SET r_con = %s WHERE r_id = %s;',
                (SENTINEL_VALUE, test_rid),
            )
            assert cur.rowcount == 1, "Should have updated exactly one stage row"
            print(yellow(f"  → Wrote sentinel into stage.r_con for r_id={test_rid}"))

            # Commit the stage edit so the upsert (in its own connection) sees it
            conn.commit()

    # ── Run the upsert engine ────────────────────────────────────────────────
    print()
    print("  Running run_upsert()…")
    stats = run_upsert(cfg, conn_string, column_map=None)
    print(f"    inserted:     {stats['inserted']}")
    print(f"    updated:      {stats['updated']}")
    print(f"    soft_deleted: {stats['soft_deleted']}")
    print(f"    un_deleted:   {stats['un_deleted']}")
    print()

    # ── Verify the sentinel landed in the target ─────────────────────────────
    with get_db_connection(conn_string) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT r_con, r_length, ST_Length(geom::geography) AS computed_length '
                f'FROM {target} WHERE r_id = %s;',
                (test_rid,),
            )
            row = cur.fetchone()
            target_after, r_length, computed_length = row

            # ASSERTION 1: sentinel propagated
            print("  Assertions:")
            if target_after == SENTINEL_VALUE:
                print(green(f"    ✓ r_con propagated: {target_after!r}"))
            else:
                print(red(f"    ✗ r_con DID NOT propagate."))
                print(red(f"      Expected: {SENTINEL_VALUE!r}"))
                print(red(f"      Got:      {target_after!r}"))
                failures.append("r_con propagation")

            # ASSERTION 2: stats reported updates, not inserts
            if stats["updated"] > 0:
                print(green(f"    ✓ Stats reported updates: {stats['updated']}"))
            else:
                print(red(f"    ✗ Stats reported zero updates ({stats['updated']}). "
                          f"Engine may still be misreporting."))
                failures.append("update counter")

            # ASSERTION 3: r_length matches computed
            if r_length is not None and computed_length is not None:
                drift = abs(float(r_length) - float(computed_length))
                if drift < 0.01:
                    print(green(f"    ✓ r_length ({r_length:.2f}m) matches "
                                f"ST_Length (drift={drift:.4f}m)"))
                else:
                    print(red(f"    ✗ r_length drift too large: "
                              f"stored={r_length}, computed={computed_length}, drift={drift}"))
                    failures.append("r_length drift")
            else:
                print(yellow(f"    ⚠ r_length or computed_length is NULL — skipping drift check"))

            # ── Restore the original value ───────────────────────────────────
            cur.execute(
                f'UPDATE {stage} SET r_con = %s WHERE r_id = %s;',
                (original_rcon, test_rid),
            )
            cur.execute(
                f'UPDATE {target} SET r_con = %s WHERE r_id = %s;',
                (original_rcon, test_rid),
            )
            conn.commit()
            print()
            print(yellow(f"  → Restored r_con={original_rcon!r} for r_id={test_rid}"))

    # ── Final verdict ────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    if failures:
        print(red(f"  RESULT: FAILED ({len(failures)} assertion(s) failed)"))
        for f in failures:
            print(red(f"    - {f}"))
        print("=" * 70)
        sys.exit(1)
    else:
        print(green("  RESULT: ALL ASSERTIONS PASSED"))
        print(green("  The upsert engine correctly propagates attribute edits."))
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()
