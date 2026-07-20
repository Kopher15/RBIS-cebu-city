import json
import os
import time
from datetime import datetime, timezone
from lib.logger import get_logger
from services.gpkg_loader import load_gpkg_to_stage
from services.schema_reconciler import reconcile
from services.backup_service import create_backup
from services.upsert_engine import run_upsert


def _write_last_sync(cfg, results, logger):
    """Write last-sync.json to the RBIS data directory after a successful sync.

    The file is read by the dashboard's inspection bar to display
    "Last updated <date>". It is committed to GitHub alongside roads.geojson
    as part of the normal refresh workflow.

    Only writes for the 'local' destination — that is the authoritative source
    the export script reads from. Cloud destinations are ignored here.

    File location: cfg["rbis_data_dir"] / last-sync.json
    Falls back silently if rbis_data_dir is not set in config (older configs).
    """
    rbis_data_dir = cfg.get("rbis_data_dir")
    if not rbis_data_dir:
        logger.warning("rbis_data_dir not set in config — skipping last-sync.json write")
        return

    # Pull stats from the local destination result only
    local_result = next((r for r in results if r["dest"] == "local"), None)
    if not local_result or local_result["status"] != "success":
        logger.warning("Local destination did not succeed — skipping last-sync.json write")
        return

    stats = local_result.get("stats", {})
    total_segments = (
        stats.get("inserted", 0)
        + stats.get("updated", 0)
    )

    now = datetime.now()
    payload = {
        "_comment": "Written by sync_orchestrator.py after every successful local sync. "
                    "Commit this file to GitHub alongside roads.geojson. "
                    "The dashboard inspection bar reads last_sync to display 'Last updated <date>'.",
        "last_sync":  now.strftime("%Y-%m-%d"),          # date only — what the dashboard shows
        "timestamp":  now.strftime("%Y-%m-%dT%H:%M:%S"), # full datetime — for health logs / future use
        "segments_updated": total_segments
    }

    out_path = os.path.join(rbis_data_dir, "last-sync.json")
    try:
        os.makedirs(rbis_data_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")  # trailing newline — git-friendly
        logger.info(f"last-sync.json written -> {out_path}")
    except Exception as e:
        # Non-fatal: log the error but don't fail the whole sync over a metadata file
        logger.error(f"Failed to write last-sync.json: {e}")


def run(cfg):
    logger = get_logger(cfg["log_dir"], "sync_orchestrator")
    start_time = time.time()
    results = []

    try:
        # Loop through all destinations (Local and Cloud)
        for dest in cfg["destinations"]:
            logger.info(f"--- Starting Sync for: {dest['name']} ---")
            conn_str = dest["conn_string"]

            # Step 1: Load GPKG to the specific destination's stage table
            # This ensures 'public.road_inventory_stage' exists on this specific DB
            load_gpkg_to_stage(cfg, conn_str)

            # Step 2: Reconcile schema and create backup
            column_map = reconcile(cfg, conn_str)
            backup_table = create_backup(cfg, conn_str)

            # Step 3: Run the Upsert from stage to prod
            stats = run_upsert(cfg, conn_str, column_map)

            results.append({
                "dest": dest["name"],
                "status": "success",
                "stats": stats,
                "backup": backup_table
            })
            logger.info(f"--- Finished Sync for: {dest['name']} ---")

        # Step 4: Write last-sync.json to the RBIS repo's data folder.
        # Done after all destinations loop so we only write on full success.
        _write_last_sync(cfg, results, logger)

        elapsed = time.time() - start_time
        return {"status": "success", "results": results, "elapsed": round(elapsed, 2)}

    except Exception as e:
        logger.error(f"Sync failed: {str(e)}")
        return {"status": "failed", "error": str(e)}
